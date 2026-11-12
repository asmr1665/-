import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="시아 주식 발굴 V3 수정판", page_icon="📈", layout="wide")
st.title("📈 시아 주식 발굴 V3 — 수정판")
st.caption("일봉·주봉·3분봉·5분봉 및 후보 TOP 3 | Yahoo Finance 지연 시세, 실시간 보장 아님")

WATCH = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "NAVER": "035420.KS",
         "현대차": "005380.KS", "기아": "000270.KS", "GS건설": "006360.KS",
         "펄어비스": "263750.KQ", "카카오": "035720.KS", "로보티즈": "108490.KQ"}

@st.cache_data(ttl=600, show_spinner=False)
def prices(symbol, interval="1d", period="1y"):
    df = yf.download(symbol, interval=interval, period=period,
                     auto_adjust=True, progress=False, threads=False)
    if df is None or df.empty:
        raise ValueError("시세 데이터 없음 (제공처 제한 또는 종목 코드 확인)")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df.columns = [str(x).strip().lower() for x in df.columns]
    time_col = next((x for x in ("datetime", "date", "time") if x in df.columns), None)
    if time_col is None:
        raise ValueError("날짜·시간 열을 찾을 수 없습니다")
    df = df.rename(columns={time_col: "time"})
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    if df.empty:
        raise ValueError("유효한 시세 데이터 없음")
    return df.sort_values("time").reset_index(drop=True)

def score(df, name, symbol):
    if len(df) < 65:
        return None
    c, v = df["close"], df["volume"]
    ma5, ma20, ma60 = (c.rolling(n).mean() for n in (5, 20, 60))
    ch5 = (c.iloc[-1] / c.iloc[-6] - 1) * 100
    ch20 = (c.iloc[-1] / c.iloc[-21] - 1) * 100
    ratio = v.tail(5).mean() / max(v.iloc[-25:-5].mean(), 1)
    peak = df["high"].iloc[-21:-1].max()
    consolidation = c.tail(10).max() / max(c.tail(10).min(), 0.01) < 1.10
    points = (25 if ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] else 0)
    points += 20 if 1.1 <= ratio <= 3.5 else 0
    points += 20 if -1 <= ch5 <= 8 else 0
    points += 15 if .97 <= c.iloc[-1] / peak <= 1.03 else 0
    points += 10 if -5 <= ch20 <= 15 else 0
    points += 10 if consolidation else 0
    last = float(c.iloc[-1])
    stop = min(float(df["low"].tail(5).min()), last * .96)
    risk = max(last - stop, last * .01)
    return {"종목": name, "코드": symbol, "기준일": str(df["time"].iloc[-1])[:10],
            "종가": round(last), "기술점수": points, "5일등락%": round(ch5, 2),
            "거래량배율": round(ratio, 2), "관심매수가": round(min(last, ma5.iloc[-1])),
            "목표가(예시)": round(last + 2 * risk), "손절가(예시)": round(stop)}

st.info("현재 버전은 시세가 확인되는 선택 종목만 분석합니다. 코스피·코스닥 전 종목 자동 검색과 키움 실시간 API는 아직 연결되지 않았습니다.")
extra = st.text_input("추가 종목 코드 (예: 005930.KS, 263750.KQ)")
selected = st.multiselect("분석 대상", list(WATCH), default=["삼성전자", "NAVER", "GS건설"])
minimum = st.slider("최소 기술점수", 0, 100, 40, 5)
if st.button("📊 후보 분석", type="primary"):
    symbols = {name: WATCH[name] for name in selected}
    if extra.strip():
        symbols[extra.strip().upper()] = extra.strip().upper()
    results, errors = [], []
    progress = st.progress(0)
    for i, (name, symbol) in enumerate(symbols.items()):
        try:
            result = score(prices(symbol), name, symbol)
            if result:
                results.append(result)
            else:
                errors.append(f"{name}: 분석 기간 부족")
        except Exception as e:
            errors.append(f"{name}: {e}")
        progress.progress((i + 1) / max(len(symbols), 1))
    st.session_state["results"] = results
    st.session_state["errors"] = errors

if "results" in st.session_state:
    ranked = sorted(st.session_state["results"], key=lambda x: x["기술점수"], reverse=True)
    candidates = [r for r in ranked if r["기술점수"] >= minimum]
    st.subheader("🏆 후보 TOP 3")
    if candidates:
        st.dataframe(pd.DataFrame(candidates[:3]), hide_index=True, use_container_width=True)
        st.write(f"최우선 관찰: **{candidates[0]['종목']}** (점수 기준, 매수 권유 아님)")
    else:
        st.warning("기준을 충족한 후보가 없습니다.")
    for error in st.session_state["errors"]:
        st.warning(error)

st.divider()
st.subheader("📉 종목별 차트")
name = st.selectbox("차트 종목", list(WATCH))
tf = st.radio("차트 종류", ["일봉", "주봉", "3분봉", "5분봉"], horizontal=True)
if st.button("차트 불러오기"):
    try:
        if tf in ("일봉", "주봉"):
            df = prices(WATCH[name], "1d", "1y")
            if tf == "주봉":
                df = (df.set_index("time").resample("W-FRI")
                      .agg({"open": "first", "high": "max", "low": "min",
                            "close": "last", "volume": "sum"})
                      .dropna(subset=["open", "close"]).reset_index())
        elif tf == "5분봉":
            df = prices(WATCH[name], "5m", "1mo")
        else:
            df = prices(WATCH[name], "1m", "5d")
            df = (df.set_index("time").resample("3min")
                  .agg({"open": "first", "high": "max", "low": "min",
                        "close": "last", "volume": "sum"})
                  .dropna(subset=["open", "close"]).reset_index())
        if df.empty:
            raise ValueError("표시할 봉이 없습니다")
        fig = go.Figure(go.Candlestick(x=df["time"], open=df["open"],
                                      high=df["high"], low=df["low"], close=df["close"]))
        for n in (5, 20, 60):
            fig.add_trace(go.Scatter(x=df["time"], y=df["close"].rolling(n).mean(),
                                     name=f"{n}이평선"))
        fig.update_layout(height=650, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"최종 데이터 시각: {df['time'].iloc[-1]} | {len(df)}개 봉 | Yahoo Finance")
    except Exception as e:
        st.error(f"차트 조회 실패: {type(e).__name__}: {e}")
