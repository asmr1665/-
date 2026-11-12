
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="급등 전 후보 탐색기 2.0", layout="wide")
st.title("📈 급등 전 후보 탐색기 2.0")
st.caption("5~7거래일 관찰용 조건검색 · 실시간 시세 미연결 · 투자 권유 아님")
f=st.file_uploader("일별 주가 CSV 업로드", type="csv")
st.info("필수: date,ticker,name,close,volume | 권장: open,high,low,foreign_net,institution_net,sector,news_score")
if f is None: st.stop()
try:
    df=pd.read_csv(f,dtype={"ticker":str})
    req={"date","ticker","name","close","volume"}
    if req-set(df.columns): st.error(f"필수 열 누락: {req-set(df.columns)}"); st.stop()
    df["date"]=pd.to_datetime(df["date"],errors="coerce")
    for c in ["open","high","low","close","volume","foreign_net","institution_net","news_score"]:
        if c not in df: df[c]=np.nan
        df[c]=pd.to_numeric(df[c],errors="coerce")
    if "sector" not in df: df["sector"]="미분류"
    df=df.dropna(subset=["date","ticker","close","volume"]).sort_values(["ticker","date"]).drop_duplicates(["ticker","date"],keep="last")
    if df.empty: st.error("유효한 데이터가 없습니다."); st.stop()
    threshold=st.sidebar.slider("최소 거래량 증가배수",1.0,3.0,1.2,0.1)
    min_score=st.sidebar.slider("최소 종합점수",0,100,50,5)
    results=[]
    for ticker,g in df.groupby("ticker"):
        g=g.tail(130).copy()
        if len(g)<35 or (g.close<=0).any() or (g.volume<0).any(): continue
        c=g.close; v=g.volume; last=g.iloc[-1]
        ma5=c.rolling(5).mean(); ma20=c.rolling(20).mean(); ma60=c.rolling(60).mean()
        vol_ratio=v.tail(5).mean()/max(v.tail(20).mean(),1)
        ret5=c.iloc[-1]/c.iloc[-6]-1
        near_high=c.iloc[-1]/c.tail(20).max()
        golden=bool(ma5.iloc[-2]<=ma20.iloc[-2] and ma5.iloc[-1]>ma20.iloc[-1])
        trend=bool(c.iloc[-1]>=ma20.iloc[-1] and ma5.iloc[-1]>=ma20.iloc[-1])
        # '공구리'는 공식 표준지표가 아니므로 20일선 근처 횡보+변동성 축소로 근사
        consolidation=bool(c.tail(10).max()/c.tail(10).min()-1<0.10 and abs(c.iloc[-1]/ma20.iloc[-1]-1)<0.05)
        support=float(c.tail(20).min()); resistance=float(c.tail(20).max())
        foreign=g.foreign_net.tail(5).sum(min_count=1); inst=g.institution_net.tail(5).sum(min_count=1)
        flow=int(pd.notna(foreign) and foreign>0)+int(pd.notna(inst) and inst>0)
        news=last.news_score
        # 점수는 검증 전 휴리스틱; 뉴스 점수는 외부에서 -1~1로 공급된 경우만 반영
        score=min(vol_ratio/2,1)*25+int(trend)*20+int(golden)*10+int(consolidation)*15+flow*10+max(0,min((near_high-.9)/.1,1))*10
        if pd.notna(news): score+=max(0,min(float(news),1))*10
        score=min(round(score,1),100)
        if vol_ratio<threshold or score<min_score: continue
        results.append({"종목코드":ticker,"종목명":last["name"],"기준일":last.date.date(),
          "업종":last.sector,"종가":round(float(c.iloc[-1]),2),"점수":score,
          "거래량배수":round(vol_ratio,2),"5일수익률(%)":round(ret5*100,2),
          "골든크로스":golden,"추세양호":trend,"공구리근사":consolidation,
          "외국인5일순매수":foreign,"기관5일순매수":inst,
          "지지선(참고)":round(support,2),"저항선(참고)":round(resistance,2),
          "관찰매수가(참고)":round(float(ma20.iloc[-1]),2),
          "목표가(예시+5%)":round(float(c.iloc[-1])*1.05,2),
          "손절가(예시-3%)":round(float(c.iloc[-1])*.97,2)})
    if not results: st.warning("조건에 맞는 후보가 없습니다. 기준을 완화하거나 데이터 기간을 늘려보세요."); st.stop()
    out=pd.DataFrame(results).sort_values(["점수","거래량배수"],ascending=False)
    st.subheader("상위 5개 후보")
    st.dataframe(out.head(5),use_container_width=True,hide_index=True)
    st.subheader("최종 우선 관찰 1종목")
    st.dataframe(out.head(1),use_container_width=True,hide_index=True)
    st.caption("매수가·목표가·손절가는 기계적 참고값이며 실제 주문 신호가 아닙니다. 데이터 누락 시 점수는 과소평가될 수 있습니다.")
    st.subheader("업종별 후보 평균 점수")
    st.bar_chart(out.groupby("업종")["점수"].mean())
    st.download_button("후보 CSV 다운로드",out.to_csv(index=False).encode("utf-8-sig"),"candidates_v2.csv","text/csv")
    st.subheader("매매 기록")
    with st.form("trade"):
        name=st.text_input("종목명"); buy=st.number_input("매수가",min_value=0.0); sell=st.number_input("매도가",min_value=0.0)
        if st.form_submit_button("수익률 계산"):
            if buy>0: st.metric("수익률(수수료·세금 제외)",f"{(sell/buy-1)*100:.2f}%")
            else: st.warning("매수가를 입력하세요.")
    st.warning("백테스트·뉴스 자동수집·실시간 수급·시장 전체 자동 스캔은 별도 데이터 연동이 필요합니다. 이 버전에는 포함되지 않았습니다.")
except Exception as e:
    st.error(f"데이터 처리 오류: {e}")
