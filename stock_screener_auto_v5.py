from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

from signals import MARKETS, confirm, rank, read_daily

SEOUL = ZoneInfo("Asia/Seoul")
DATA = Path(__file__).with_name("market_daily.csv")
st.set_page_config(page_title="시아 주식 분석 프로그램", layout="wide")
st.title("시아 주식 분석 프로그램")


@st.cache_data(show_spinner=False)
def analyze(payload):
    from io import BytesIO

    daily = read_daily(BytesIO(payload))
    return daily, rank(daily)


@st.cache_data(ttl=60, show_spinner=False)
def get_bars(code, market):
    ticker = yf.Ticker(f"{code}.{MARKETS[market]}")
    bars = ticker.history(period="10d", interval="5m", auto_adjust=False,
                          prepost=False, timeout=8, raise_errors=True)
    if bars.empty or bars.index.tz is None:
        return pd.DataFrame()
    bars.index = bars.index.tz_convert(SEOUL)
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    return bars.between_time("09:00", "15:25").dropna(
        subset=["Open", "High", "Low", "Close", "Volume"])


def safe_bars(row):
    try:
        return get_bars(row["code"], row["market"])
    except Exception:
        return pd.DataFrame()


def chart(bars, key, intraday=False):
    if bars.empty:
        return
    columns = ["open", "high", "low", "close", "volume"]
    bars = bars.rename(columns=str.lower)
    x = bars.index.strftime("%H:%M" if intraday else "%Y-%m-%d")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.77, .23],
                        vertical_spacing=.05)
    if bars[columns[:4]].notna().all().all():
        fig.add_trace(go.Candlestick(x=x, open=bars.open, high=bars.high,
                                      low=bars.low, close=bars.close,
                                      increasing_line_color="#D74747",
                                      decreasing_line_color="#3874B6", name="가격"), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=x, y=bars.close, name="종가"), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=bars.volume, name="거래량"), row=2, col=1)
    fig.update_xaxes(type="category", nticks=7, rangeslider_visible=False)
    fig.update_layout(height=370, showlegend=False, margin=dict(l=8, r=8, t=8, b=8))
    st.plotly_chart(fig, use_container_width=True, key=key)


upload = st.file_uploader("일봉 CSV 직접 열기", type="csv")
if upload is None and not DATA.exists():
    st.info("시장 일봉이 필요합니다. GitHub Actions의 수집 작업을 실행하거나 market_daily.csv를 올려주세요.")
    st.stop()
try:
    daily, ranked = analyze(upload.getvalue() if upload is not None else DATA.read_bytes())
except (ValueError, OSError) as error:
    st.error(f"일봉을 읽지 못했습니다. {error}")
    st.stop()

latest = daily.date.max().date()
universe = daily[daily.date.dt.date == latest]
counts = universe.groupby("market").code.nunique()
minimums = {"KOSPI": 500, "KOSDAQ": 900}
coverage_ok = all(counts.get(market, 0) >= limit for market, limit in minimums.items())
auto = st.toggle("장중 60초마다 시세 조회", value=True)
st.caption(f"일봉 {latest} · 코스피 {counts.get('KOSPI', 0):,}개 · "
           f"코스닥 {counts.get('KOSDAQ', 0):,}개 · 61일 이상 분석 {len(ranked):,}개")
if not coverage_ok:
    st.warning("시장별 일봉 수집이 충분하지 않아 후보 순위를 보류합니다. 종목 조회는 사용할 수 있습니다.")

query = st.text_input("종목명 또는 종목코드 검색").strip()
selection = universe[["name", "market", "code"]].drop_duplicates()
if query:
    selection = selection[selection.name.str.contains(query, case=False, regex=False)
                          | selection.code.str.contains(query, regex=False)]
symbols = list(selection.sort_values("name").itertuples(index=False, name=None))
chosen = st.selectbox("차트 종목", symbols, index=None,
                      format_func=lambda item: f"{item[0]} ({item[2]}) · {item[1]}")
if chosen is not None:
    name, market, code = chosen
    detail = daily[(daily.code == code) & (daily.market == market)]
    cutoff = pd.Timestamp(latest) - pd.DateOffset(months=6)
    st.subheader(f"{name} · 6개월 일봉")
    chart(detail[detail.date >= cutoff].set_index("date"), "daily")


@st.fragment(run_every="60s" if auto else None)
def session_view():
    st.button("시세 다시 조회")
    now = datetime.now(SEOUL)
    day = now.date()
    # On Monday, Friday is normally the preceding session. Allow a single
    # additional business day for a closure, and show the observed date.
    prior_day = (pd.Timestamp(day) - pd.offsets.BDay(2)).date()
    regular = now.weekday() < 5 and time(9) <= now.time() < time(15, 30)
    daily_ok = prior_day <= latest <= day and (not regular or latest < day)
    watch = (ranked[ranked.eligible].head(12).to_dict("records")
             if coverage_ok and daily_ok and not ranked.empty else [])
    fetched = {}
    if regular or chosen:
        requests = watch.copy() if regular else []
        if chosen and all((r["market"], r["code"]) != (chosen[1], chosen[2]) for r in requests):
            requests.append(dict(market=chosen[1], code=chosen[2]))
        if requests:
            with ThreadPoolExecutor(max_workers=4) as pool:
                for row, bars in zip(requests, pool.map(safe_bars, requests)):
                    if not bars.empty:
                        bars = bars[bars.index + pd.Timedelta(minutes=5) <= now]
                    fetched[(row["market"], row["code"])] = bars
    st.caption("장중 시세 Yahoo Finance 5분봉 · 지연 가능 · 한국시간")
    if not daily_ok:
        st.warning("장중에는 전 거래일까지의 일봉이 필요합니다. 일봉 기준일을 확인해 주세요.")
    candidates = []
    for row in watch:
        bars = fetched.get((row["market"], row["code"]), pd.DataFrame())
        status, ratio = ("장외 · 일봉 관찰", None)
        updated = "—"
        if regular:
            status = "장중 시세 미확인"
            if not bars.empty:
                status, ratio = confirm(bars, row, now)
        if not bars.empty:
            updated = (bars.index[-1] + pd.Timedelta(minutes=5)).strftime("%m-%d %H:%M")
        candidates.append((row, status, ratio, updated))
    candidates.sort(key=lambda item: item[1] == "매수 검토", reverse=True)
    st.subheader("급등 전 관찰 후보")
    if not candidates:
        st.info("표시할 후보가 없습니다.")
    else:
        for row, status, ratio, updated in candidates[:3]:
            st.markdown(f"**{row['name']} ({row['code']}) · {status}**")
            st.caption(f"{row['reasons']} · 점수 {row['score']} · 5분봉 마감 {updated}")
            entry = f"{row['top']:,.0f}원"
            if not row["measured_high"]:
                entry += " (종가 기준 참고선)"
            st.write(f"돌파 관찰 {entry} · 지지 {row['support']:,.0f}원")
            if row["measured_high"] and pd.notna(row["stop"]):
                st.caption(f"손절 관찰 {row['stop']:,.0f}원 · 목표 관찰 {row['target']:,.0f}원")
            if ratio is not None:
                st.caption(f"같은 시간대 누적 거래량 {ratio:.2f}배")
        confirmed = [row for row, status, _, _ in candidates if status == "매수 검토"]
        if confirmed:
            st.success(f"최종 매수 검토 1순위 · {confirmed[0]['name']}")
        else:
            st.info("매수 검토 조건 충족 종목 없음 · 관망")
    if chosen:
        bars = fetched.get((chosen[1], chosen[2]), pd.DataFrame())
        if bars.empty:
            st.warning("이 종목의 5분봉을 확인할 수 없습니다.")
        else:
            bar_day = bars.index[-1].date()
            st.subheader(f"{chosen[0]} · {bar_day} 5분봉")
            chart(bars[bars.index.date == bar_day], "intraday")


session_view()
