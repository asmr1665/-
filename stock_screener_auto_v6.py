"""Sia Stock Screener V6 — research dashboard; no order execution."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf
from signals import MARKETS, rank, read_daily

SEOUL = ZoneInfo('Asia/Seoul')
DATA = Path(__file__).with_name('market_daily.csv')
st.set_page_config(page_title='시아 주식 발굴 V6', page_icon='📈', layout='wide')
st.markdown('''<style>.block-container{padding-top:1.1rem;max-width:1250px}div[data-testid="stMetric"]{border:1px solid #7773;border-radius:12px;padding:12px}</style>''', unsafe_allow_html=True)
st.title('📈 시아 주식 발굴 V6')
st.caption('급등 전 관찰 후보 · 조건 기반 선별 · 매수 추천이나 수익 보장 아님')

@st.cache_data(show_spinner=False)
def parse_data(payload):
    daily = read_daily(BytesIO(payload))
    return daily, rank(daily)

@st.cache_data(ttl=180, show_spinner=False)
def fetch_chart(code, market, interval):
    symbol = f'{code}.{MARKETS[market]}'
    if interval == '3분':
        period, api_interval = '5d', '1m'
    elif interval == '5분':
        period, api_interval = '5d', '5m'
    else:
        period, api_interval = '6mo', '1d'
    bars = yf.Ticker(symbol).history(period=period, interval=api_interval, auto_adjust=False, timeout=12)
    if bars.empty:
        return pd.DataFrame()
    bars = bars.rename(columns=str.lower)
    bars = bars[['open','high','low','close','volume']].dropna().sort_index()
    if bars.index.tz is not None:
        bars.index = bars.index.tz_convert(SEOUL)
    if interval == '3분':
        # 3-minute candles from source 1-minute bars; incomplete candle excluded.
        bars = bars.resample('3min', origin='start_day', offset='0min', label='left', closed='left').agg(
            {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        now = pd.Timestamp.now(tz=SEOUL)
        bars = bars[bars.index + pd.Timedelta(minutes=3) <= now]
    if interval == '5분':
        now = pd.Timestamp.now(tz=SEOUL)
        bars = bars[bars.index + pd.Timedelta(minutes=5) <= now]
    return bars

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100/(1+rs)

def plot_chart(frame, label):
    if frame.empty:
        st.warning('이 종목의 차트 데이터를 가져오지 못했습니다. 데이터 공급원 제한일 수 있습니다.')
        return
    frame = frame.tail(180).copy()
    x = frame.index.strftime('%m-%d %H:%M' if label in ('3분','5분') else '%Y-%m-%d')
    macd = frame.close.ewm(span=12, adjust=False).mean() - frame.close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=.035,
                        row_heights=[.55,.17,.14,.14])
    fig.add_trace(go.Candlestick(x=x, open=frame.open, high=frame.high, low=frame.low,
                                  close=frame.close, name='가격'), row=1, col=1)
    for n in (5,20,60):
        if len(frame) >= n:
            fig.add_trace(go.Scatter(x=x, y=frame.close.rolling(n).mean(), name=f'{n}이평'), row=1, col=1)
    fig.add_trace(go.Bar(x=x,y=frame.volume,name='거래량'),row=2,col=1)
    fig.add_trace(go.Scatter(x=x,y=rsi(frame.close),name='RSI(14)'),row=3,col=1)
    fig.add_hline(y=70,line_dash='dot',row=3,col=1)
    fig.add_hline(y=30,line_dash='dot',row=3,col=1)
    fig.add_trace(go.Scatter(x=x,y=macd,name='MACD'),row=4,col=1)
    fig.add_trace(go.Scatter(x=x,y=signal,name='시그널'),row=4,col=1)
    fig.update_xaxes(type='category',nticks=7,rangeslider_visible=False)
    fig.update_layout(height=760,margin=dict(l=0,r=0,t=20,b=0),legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption(f'차트 최종 봉: {frame.index[-1]} · Yahoo Finance 제공, 지연·누락 가능 · 실시간 확정 시세 아님')

upload = st.file_uploader('일봉 CSV 업로드 (자동 수집 실패 시)',type='csv')
if upload is None and not DATA.exists():
    st.error('market_daily.csv가 없습니다. GitHub Actions 수집을 실행하거나 CSV를 업로드하세요.')
    st.stop()
try:
    daily, ranked = parse_data(upload.getvalue() if upload else DATA.read_bytes())
except Exception as exc:
    st.error(f'일봉 데이터 읽기 실패: {exc}')
    st.stop()
latest = daily.date.max()
market_count = daily[daily.date == latest].groupby('market').code.nunique()
coverage = market_count.get('KOSPI',0)>=500 and market_count.get('KOSDAQ',0)>=900
age = (pd.Timestamp.now(tz=SEOUL).date()-latest.date()).days
c1,c2,c3 = st.columns(3)
c1.metric('데이터 기준일',str(latest.date()))
c2.metric('코스피 종목',f"{market_count.get('KOSPI',0):,}")
c3.metric('코스닥 종목',f"{market_count.get('KOSDAQ',0):,}")
if age > 4:
    st.error(f'데이터가 {age}일 전 기준입니다. 최신 추천으로 사용하지 마세요.')
if not coverage:
    st.warning('시장 전체 수집 기준 미달입니다. TOP 후보 순위는 보류합니다.')
if ranked.empty:
    st.info('분석에 필요한 61거래일 이상 데이터가 부족합니다.')
    st.stop()

candidates = ranked[ranked.eligible].copy() if coverage and age <= 4 else ranked.iloc[0:0].copy()
if not candidates.empty:
    candidates = candidates[candidates['measured_high'] & candidates['stop'].notna()]
st.subheader('오늘의 급등 전 관찰 TOP 5')
st.caption('5~7거래일은 관찰 기간이지 상승 시점 예측이 아닙니다. 점수는 규칙 기반이며 검증된 확률이 아닙니다.')
if candidates.empty:
    st.info('오늘은 엄격한 조건을 충족하는 후보가 없습니다. 관망도 결과입니다.')
else:
    view = candidates.head(5).copy()
    view['점수'] = view.score
    view['5일 변동률(%)'] = (view.ret5*100).round(1)
    view['20일 변동률(%)'] = (view.ret20*100).round(1)
    st.dataframe(view[['name','code','market','점수','close','5일 변동률(%)','20일 변동률(%)','reasons']].rename(
        columns={'name':'종목','code':'코드','market':'시장','close':'기준 종가','reasons':'선정 이유'}),
        hide_index=True,use_container_width=True)

st.divider()
st.subheader('종목별 상세 분석')
latest_symbols = daily[daily.date==latest][['name','market','code']].drop_duplicates()
search = st.text_input('종목명 또는 6자리 종목코드 검색').strip()
if search:
    latest_symbols = latest_symbols[latest_symbols.name.str.contains(search,case=False,regex=False) |
                                    latest_symbols.code.str.contains(search,regex=False)]
options = [(r.name,r.market,r.code) for r in latest_symbols.sort_values('name').itertuples(index=False)]
if not options:
    st.info('검색 결과가 없습니다.')
    st.stop()
chosen = st.selectbox('종목 선택',options,index=None,format_func=lambda x:f'{x[0]} ({x[2]}) · {x[1]}')
if chosen:
    name,market,code = chosen
    row = ranked[(ranked.market==market)&(ranked.code==code)]
    hist = daily[(daily.market==market)&(daily.code==code)].sort_values('date')
    if not row.empty:
        r = row.iloc[0]
        st.markdown(f'**{name} · 분석 점수 {int(r.score)} / 100 (규칙 기반)**')
        st.write('선정 근거: '+(r.reasons or '현재 충족된 가점 조건 없음'))
        st.write(f'기준 종가 {r.close:,.0f}원 · 돌파 관찰선 {r.top:,.0f}원 · 지지선 {r.support:,.0f}원')
        if pd.notna(r.stop):
            st.write(f'손절 관찰선 {r.stop:,.0f}원 · 목표 관찰선 {r.target:,.0f}원 (기계적 예시, 투자 권유 아님)')
        st.caption('취소 조건: 지지선 이탈, 시초가 4% 이상 갭상승, 돌파선 3% 이상 추격, 거래량 확인 실패')
        st.write(f'외국인 5일 순매수 {r.foreign:,.0f}주 · 기관 5일 순매수 {r.institution:,.0f}주' if pd.notna(r.foreign) and pd.notna(r.institution) else '수급 데이터 일부 누락')
    interval = st.radio('차트 주기',['3분','5분','일봉','주봉'],horizontal=True)
    if interval in ('일봉','주봉'):
        bars = hist.set_index('date')[['open','high','low','close','volume']].dropna().copy()
        if interval=='주봉':
            bars = bars.resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    else:
        try:
            bars = fetch_chart(code,market,interval)
        except Exception as exc:
            st.warning(f'분봉 조회 실패: {type(exc).__name__}')
            bars = pd.DataFrame()
    plot_chart(bars,interval)
    if len(hist)>20:
        st.caption(f'일봉 RSI(14) {rsi(hist.close).iloc[-1]:.1f} · 데이터 기준 {latest.date()}')

st.divider()
st.subheader('성과 검증 — 과거 관찰 후보')
st.caption('과거 특정 시점에 사용 가능했던 일봉만으로 선별한 뒤, 이후 5·7거래일 종가 수익률을 비교합니다. 수수료·슬리피지 미반영, 매매 수익률 아님.')
if st.button('과거 1회 시점 검증 실행'):
    dates = sorted(daily.date.unique())
    if len(dates)<75:
        st.warning('검증에 필요한 데이터가 부족합니다.')
    else:
        anchor = dates[-9]  # 8 later sessions available
        past = daily[daily.date<=anchor]
        with st.spinner('과거 시점 조건 재계산 중'):
            old = rank(past)
        picks = old[old.eligible].head(5) if not old.empty else pd.DataFrame()
        records=[]
        for r in picks.itertuples(index=False):
            future = daily[(daily.code==r.code)&(daily.market==r.market)&(daily.date>anchor)].sort_values('date')
            if len(future)>=7:
                records.append({'종목':r.name,'과거 기준일':str(pd.Timestamp(anchor).date()),'당시 점수':r.score,
                                '5거래일(%)':round((future.close.iloc[4]/r.close-1)*100,2),
                                '7거래일(%)':round((future.close.iloc[6]/r.close-1)*100,2)})
        if records:
            st.dataframe(pd.DataFrame(records),hide_index=True,use_container_width=True)
            st.caption('한 시점의 소규모 예시입니다. 통계적으로 신뢰할 수 있는 백테스트는 별도 다기간 검증이 필요합니다.')
        else:
            st.info('해당 과거 시점에 검증 가능한 후보가 없었습니다.')

st.info('키움 실시간 API는 아직 연결되지 않았습니다. 현재 분봉은 Yahoo Finance 조회이며 실제 실시간 체결 데이터로 간주하지 마세요.')
