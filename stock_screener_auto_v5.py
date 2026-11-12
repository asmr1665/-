import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="전체시장 자동 스크리너", layout="wide")
st.title("코스피·코스닥 전체시장 자동 스크리너")
st.caption("매 거래일 종가 기준 · 자동 수집은 GitHub Actions에서 수행 · 투자 참고용")
data = Path(__file__).parent / "market_daily.csv"
if not data.exists():
    st.error("아직 시장 데이터가 수집되지 않았습니다. GitHub Actions의 수집 결과를 확인하세요.")
    st.stop()
df = pd.read_csv(data, dtype={"code":str}, parse_dates=["date"])
required = ["date","code","name","market","close","volume","foreign_net","institution_net"]
if any(c not in df for c in required):
    st.error("데이터 형식이 맞지 않습니다. 수집 파일을 확인하세요.")
    st.stop()
df = df.dropna(subset=required).copy()
latest = df.date.max()
st.write(f"데이터 기준일: {latest.date()} | 분석 대상: {df.code.nunique():,}종목")
if latest.date() < (datetime.now(ZoneInfo("Asia/Seoul")).date()-timedelta(days=5)):
    st.error("데이터가 5일 넘게 갱신되지 않아 추천을 중단합니다.")
    st.stop()
if df.code.nunique() < 1500:
    st.error("전체시장 종목 수집이 불완전합니다. 추천을 중단합니다.")
    st.stop()
out=[]
for code,g in df.groupby("code"):
    g=g.sort_values("date")
    if len(g)<65 or g.date.iloc[-1]!=latest: continue
    c=g.close.astype(float)
    v=g.volume.astype(float)
    if c.min()<=0 or v.iloc[-25:-5].mean()<=0: continue
    ma5,ma20,ma60=c.tail(5).mean(),c.tail(20).mean(),c.tail(60).mean()
    ret5=c.iloc[-1]/c.iloc[-6]-1
    ret20=c.iloc[-1]/c.iloc[-21]-1
    vr=v.tail(5).mean()/v.iloc[-25:-5].mean()
    f=g.foreign_net.tail(5).sum()
    i=g.institution_net.tail(5).sum()
    eligible=ma5>=ma20>=ma60 and -.03<=ret5<=.08 and ret20<=.20 and vr>=1 and f>0 and i>0 and c.iloc[-1]*v.iloc[-1]>=1e9
    score=int(ma5>=ma20>=ma60)*25+min(vr,3)*10+int(f>0)*15+int(i>0)*15+int(0<=ret5<=.05)*15
    out.append({"종목코드":code,"종목명":g.name.iloc[-1],"시장":g.market.iloc[-1],
                "종가":int(c.iloc[-1]),"5일등락률(%)":round(ret5*100,2),
                "거래량비율":round(vr,2),"외국인5일순매수":int(f),
                "기관5일순매수":int(i),"점수":round(score,1),"조건통과":eligible})
if not out:
    st.error("충분한 종목별 이력이 없습니다. 추천을 중단합니다.")
    st.stop()
result=pd.DataFrame(out).sort_values("점수",ascending=False)
st.subheader("전체 분석 종목")
st.dataframe(result,hide_index=True,use_container_width=True)
picks=result[result["조건통과"]].head(3)
st.subheader("조건 통과 상위 3개")
if picks.empty:
    st.warning("조건 통과 종목 없음. 무리하게 추천하지 않습니다.")
else:
    st.dataframe(picks,hide_index=True,use_container_width=True)
    first=picks.iloc[0]
    st.write(f"최종 1순위: {first['종목명']} ({first['종목코드']})")
    st.caption("이 순위는 규칙 기반 선별 결과이며 5~7일 상승을 예측하거나 보장하지 않습니다.")
