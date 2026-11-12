import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta

st.set_page_config(page_title="급등 전 후보 탐색기 3.0", layout="wide")
st.title("📈 급등 전 후보 탐색기 3.0")
st.caption("실제 일별 시세 기반 관찰 후보 · 15분 지연 또는 전일 데이터 가능 · 투자 권유 아님")

@st.cache_data(ttl=3600, show_spinner=False)
def get_data(ticker, start, end):
    import yfinance as yf
    x = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, threads=False)
    if x.empty:
        return None
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    x = x.reset_index()
    x.columns = [str(c).lower() for c in x.columns]
    return x

def screen(df, name, ticker):
    if df is None or len(df) < 65:
        return None
    d=df.copy().sort_values("date")
    for col in ("close","high","low","volume"):
        d[col]=pd.to_numeric(d[col],errors="coerce")
    d=d.dropna(subset=["close","volume"])
    if len(d)<65: return None
    c=d["close"]; v=d["volume"]
    ma5=c.rolling(5).mean().iloc[-1]
    ma20=c.rolling(20).mean().iloc[-1]
    ma60=c.rolling(60).mean().iloc[-1]
    vol_ratio=float(v.iloc[-5:].mean()/max(v.iloc[-25:-5].mean(),1))
    change5=float((c.iloc[-1]/c.iloc[-6]-1)*100)
    change20=float((c.iloc[-1]/c.iloc[-21]-1)*100)
    peak20=float(d["high"].iloc[-21:-1].max())
    breakout=float(c.iloc[-1]/peak20)
    score=0
    score+=25 if ma5>ma20>ma60 else 0
    score+=20 if 1.1<=vol_ratio<=3.5 else 0
    score+=20 if -1<=change5<=8 else 0
    score+=15 if 0.97<=breakout<=1.03 else 0
    score+=10 if -5<=change20<=15 else 0
    score+=10 if c.iloc[-1]>ma20 else 0
    price=float(c.iloc[-1])
    low5=float(d["low"].iloc[-5:].min())
    stop=min(low5,price*.96)
    risk=max(price-stop,price*.01)
    return dict(종목=name,코드=ticker,기준일=str(d["date"].iloc[-1])[:10],
                종가=round(price),점수=score,거래량배율=round(vol_ratio,2),
                **{"5일변동(%)":round(change5,2)},
                관심매수가=round(min(price,ma5)),목표가=round(price+2*risk),
                손절가=round(stop),취소조건="종가가 20일선 이탈 또는 거래량 급감")

st.info("이 버전은 선택한 종목의 실제 일봉을 자동 조회합니다. 한국 전체 상장종목을 전수 검색하거나 실시간 매매 신호를 제공하지 않습니다.")
universe={
    "삼성전자":"005930.KS","SK하이닉스":"000660.KS","NAVER":"035420.KS",
    "현대차":"005380.KS","기아":"000270.KS","LG에너지솔루션":"373220.KS",
    "셀트리온":"068270.KS","한화에어로스페이스":"012450.KS",
    "두산에너빌리티":"034020.KS","카카오":"035720.KS",
    "삼성전기":"009150.KS","포스코퓨처엠":"003670.KS",
}
selected=st.multiselect("분석할 종목 (최대 12개)",list(universe),default=list(universe)[:6])
threshold=st.slider("최소 후보 점수",0,100,40,5)
if st.button("실제 일봉 조회하고 분석",type="primary"):
    results=[]
    failures=[]
    for name in selected[:12]:
        ticker=universe[name]
        try:
            df=get_data(ticker,(date.today()-timedelta(days=240)).isoformat(),(date.today()+timedelta(days=1)).isoformat())
            r=screen(df,name,ticker)
            if r: results.append(r)
            else: failures.append(name)
        except Exception:
            failures.append(name)
    if results:
        all_df=pd.DataFrame(results).sort_values("점수",ascending=False)
        st.subheader("관찰 후보 TOP 3")
        filtered=all_df[all_df["점수"]>=threshold].head(3)
        if filtered.empty:
            st.warning("설정 점수 이상인 후보가 없습니다. 점수를 낮춰 비교해보세요.")
        else:
            st.dataframe(filtered,hide_index=True,use_container_width=True)
            st.write("가장 높은 관찰 점수:",filtered.iloc[0]["종목"],"— 매수 확정 신호가 아닙니다.")
        with st.expander("분석한 전체 종목"):
            st.dataframe(all_df,hide_index=True,use_container_width=True)
    else:
        st.error("조회 결과가 없습니다. 인터넷 연결 또는 시세 제공 상태를 확인해 주세요.")
    if failures:
        st.warning("조회 실패 또는 데이터 부족: "+", ".join(failures))
st.caption("가격은 거래소 공식 실시간 시세가 아닙니다. 목표가/손절가는 단순 규칙 예시이며 수익을 보장하지 않습니다.")
