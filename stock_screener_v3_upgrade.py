import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="시아 주식 발굴 V3", page_icon="📈", layout="wide")
st.title("📈 시아 주식 발굴 V3")
st.caption("급등 전 후보 + 후지모토 투자 원칙 참고 + 3분/5분/일/주봉 차트 | 정보 제공용, 매매 보장 아님")

UNIVERSE = {
 "삼성전자":"005930.KS","SK하이닉스":"000660.KS","NAVER":"035420.KS",
 "현대차":"005380.KS","기아":"000270.KS","LG에너지솔루션":"373220.KS",
 "셀트리온":"068270.KS","한화에어로스페이스":"012450.KS",
 "두산에너빌리티":"034020.KS","카카오":"035720.KS",
 "삼성전기":"009150.KS","포스코퓨처엠":"003670.KS",
 "GS건설":"006360.KS","펄어비스":"263750.KQ",
 "제주항공":"089590.KS","대동기어":"008830.KQ",
 "대한광통신":"010170.KQ","로보티즈":"108490.KQ",
}
@st.cache_data(ttl=900,show_spinner=False)
def prices(symbol,interval="1d",period="1y"):
 import yfinance as yf
 raw=yf.download(symbol,interval=interval,period=period,auto_adjust=True,progress=False,threads=False)
 if raw is None or raw.empty:
  raise ValueError("시세 제공처에서 데이터가 반환되지 않았습니다.")
 if isinstance(raw.columns,pd.MultiIndex):
  raw.columns=raw.columns.get_level_values(0)
 raw=raw.rename(columns=str.lower)
 raw=raw.reset_index()
 date_col="datetime" if "datetime" in raw.columns else "date"
 raw=raw.rename(columns={date_col:"time"})
 for k in ["open","high","low","close","volume"]:
  raw[k]=pd.to_numeric(raw[k],errors="coerce")
 raw=raw.dropna(subset=["time","open","high","low","close"]).sort_values("time")
 if raw.empty: raise ValueError("유효한 OHLC 데이터가 없습니다.")
 return raw

@st.cache_data(ttl=86400,show_spinner=False)
def fundamentals(symbol):
 import yfinance as yf
 try:
  info=yf.Ticker(symbol).info
  return {k:info.get(k) for k in ["trailingPE","priceToBook","dividendYield","revenueGrowth","earningsGrowth"]}
 except Exception:
  return {}

def calc_rsi(s,n=14):
 delta=s.diff()
 up=delta.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
 down=(-delta.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
 rs=up/down.replace(0,np.nan)
 return (100-100/(1+rs)).fillna(50)

def analyze(d,name,symbol,include_fund=True):
 if len(d)<65:return None
 d=d.copy()
 c=d.close;v=d.volume
 ma5=c.rolling(5).mean();ma20=c.rolling(20).mean();ma60=c.rolling(60).mean()
 ratio=float(v.tail(5).mean()/max(v.iloc[-25:-5].mean(),1))
 change5=float((c.iloc[-1]/c.iloc[-6]-1)*100)
 change20=float((c.iloc[-1]/c.iloc[-21]-1)*100)
 peak=float(d.high.iloc[-21:-1].max())
 rsi=float(calc_rsi(c).iloc[-1])
 golden=bool(ma5.iloc[-2]<=ma20.iloc[-2] and ma5.iloc[-1]>ma20.iloc[-1])
 consolidation=bool(c.tail(10).max()/c.tail(10).min()-1<.10)
 technical=(25 if ma5.iloc[-1]>ma20.iloc[-1]>ma60.iloc[-1] else 0)
 technical+=20 if 1.1<=ratio<=3.5 else 0
 technical+=20 if -1<=change5<=8 else 0
 technical+=15 if .97<=c.iloc[-1]/peak<=1.03 else 0
 technical+=10 if -5<=change20<=15 else 0
 technical+=10 if golden or consolidation else 0
 f=fundamentals(symbol) if include_fund else {}
 # 후지모토 참고: 공개적으로 알려진 가치·실적·과열회피 원칙을 기계적으로 근사한 자체 점수
 metrics=[("PER",f.get("trailingPE"),lambda x:0<x<=20),
          ("PBR",f.get("priceToBook"),lambda x:0<x<=2),
          ("매출성장",f.get("revenueGrowth"),lambda x:x>0),
          ("이익성장",f.get("earningsGrowth"),lambda x:x>0)]
 known=[fn(float(val)) for _,val,fn in metrics if isinstance(val,(int,float)) and np.isfinite(val)]
 known.append(35<=rsi<=65)
 fundamental=round(sum(known)/len(known)*100)
 combined=round(.65*technical+.35*fundamental)
 price=float(c.iloc[-1])
 stop=min(float(d.low.tail(5).min()),price*.96)
 risk=max(price-stop,price*.01)
 return {"종목":name,"코드":symbol,"기준일":str(d.time.iloc[-1])[:10],
         "종가":round(price),"통합점수":combined,"기술점수":technical,
         "후지모토참고점수":fundamental,"RSI":round(rsi,1),
         "거래량배율":round(ratio,2),"5일등락%":round(change5,2),
         "골든크로스":golden,"관심매수가":round(min(price,float(ma5.iloc[-1]))),
         "목표가(예시)":round(price+2*risk),"손절가(예시)":round(stop),
         "매수취소":"20일선 이탈 또는 거래량 급감",
         "재무데이터":f,"재무확인수":len(known)-1}

def plot_candles(d,title):
 d=d.copy()
 for n in [5,20,60,120]:
  d[f"ma{n}"]=d.close.rolling(n).mean()
 d["rsi"]=calc_rsi(d.close)
 ema12=d.close.ewm(span=12,adjust=False).mean()
 ema26=d.close.ewm(span=26,adjust=False).mean()
 d["macd"]=ema12-ema26
 d["signal"]=d.macd.ewm(span=9,adjust=False).mean()
 fig=make_subplots(rows=4,cols=1,shared_xaxes=True,vertical_spacing=.035,
                   row_heights=[.55,.18,.14,.13],
                   subplot_titles=(title,"거래량","RSI(14)","MACD"))
 fig.add_trace(go.Candlestick(x=d.time,open=d.open,high=d.high,low=d.low,close=d.close,name="캔들"),row=1,col=1)
 for n,color in [(5,"#eab308"),(20,"#3b82f6"),(60,"#a855f7"),(120,"#64748b")]:
  fig.add_trace(go.Scatter(x=d.time,y=d[f"ma{n}"],name=f"{n}이평",line=dict(color=color,width=1.5)),row=1,col=1)
 fig.add_trace(go.Bar(x=d.time,y=d.volume,name="거래량",marker_color="#64748b"),row=2,col=1)
 fig.add_trace(go.Scatter(x=d.time,y=d.rsi,name="RSI",line=dict(color="#eab308")),row=3,col=1)
 for level in [30,70]:
  fig.add_hline(y=level,line_dash="dot",line_color="gray",row=3,col=1)
 fig.add_trace(go.Scatter(x=d.time,y=d.macd,name="MACD",line=dict(color="#3b82f6")),row=4,col=1)
 fig.add_trace(go.Scatter(x=d.time,y=d.signal,name="시그널",line=dict(color="#ef4444")),row=4,col=1)
 fig.update_layout(height=850,xaxis_rangeslider_visible=False,
                   margin=dict(l=8,r=8,t=60,b=20),legend=dict(orientation="h"))
 st.plotly_chart(fig,use_container_width=True)

st.info("이 앱은 선택한 종목만 분석합니다. 코스피·코스닥 전 종목 자동 검색 및 실시간 외국인·기관 수급은 아직 연결되지 않았습니다.")
with st.expander("데이터 조회 및 제한 안내"):
 st.write("Yahoo Finance 기반 비공식 시세입니다. 지연·누락·접속 차단이 발생할 수 있습니다. 분봉은 제공처의 최근 기간 제한을 따릅니다. 주봉은 일봉을 주간 집계합니다.")
 st.write("후지모토 참고 점수는 당사자가 공개한 공식 매매 알고리즘이 아닌 자체 규칙입니다. 재무 수치가 없으면 해당 항목은 제외되므로 점수의 비교 신뢰도가 떨어집니다.")
 st.write("3분봉은 제공처가 직접 지원하지 않아 1분봉을 3분 단위로 합산합니다. 조회 실패 시 가짜 시세로 대체하지 않습니다.")

names=st.multiselect("분석할 종목",list(UNIVERSE),default=["삼성전자","NAVER","GS건설"])
extra=st.text_input("추가 종목 코드 (예: 005930.KS 또는 263750.KQ)")
minscore=st.slider("최소 후보 점수",0,100,40,5)
scan=st.button("📊 실제 일봉 조회하고 후보 분석",type="primary")
if scan:
 selected={n:UNIVERSE[n] for n in names}
 if extra.strip():selected[extra.strip()]=extra.strip().upper()
 records=[];errors=[]
 progress=st.progress(0)
 for idx,(name,sym) in enumerate(selected.items()):
  try:
   d=prices(sym,"1d","1y")
   r=analyze(d,name,sym)
   if r:records.append(r)
   else:errors.append(f"{name}: 분석에 필요한 65거래일 미만")
  except Exception as e:
   errors.append(f"{name}: {type(e).__name__} - {str(e)[:130]}")
  progress.progress((idx+1)/max(len(selected),1))
 st.session_state["results"]=records
 st.session_state["errors"]=errors
if "results" in st.session_state:
 records=st.session_state["results"]
 if records:
  ranked=sorted(records,key=lambda x:x["통합점수"],reverse=True)
  qualifying=[r for r in ranked if r["통합점수"]>=minscore]
  st.subheader("🏆 후보 TOP 3")
  if qualifying:
   display=[{k:v for k,v in r.items() if k not in ("재무데이터","재무확인수")} for r in qualifying[:3]]
   st.dataframe(pd.DataFrame(display),hide_index=True,use_container_width=True)
   st.success(f"최우선 관찰: {qualifying[0]['종목']} (점수 기반 참고, 매수 확정 신호 아님)")
  else:st.warning("현재 설정 점수 이상의 후보가 없습니다. 점수 기준을 낮춰 보세요.")
  with st.expander("전체 분석 결과"):
   st.dataframe(pd.DataFrame([{k:v for k,v in r.items() if k not in ("재무데이터","재무확인수")} for r in ranked]),hide_index=True)
  st.download_button("분석 결과 CSV 다운로드",pd.DataFrame([{k:v for k,v in r.items() if k not in ("재무데이터","재무확인수")} for r in ranked]).to_csv(index=False).encode("utf-8-sig"),"candidates_v3.csv","text/csv")
  st.caption("후지모토 참고 점수의 재무 항목은 데이터 제공처에 따라 누락될 수 있습니다.")
 else:st.error("조회 결과가 없습니다. 아래 개별 오류를 확인하세요.")
 for err in st.session_state.get("errors",[]):
  st.warning(err)

st.divider()
st.subheader("📉 종목별 3분봉 · 5분봉 · 일봉 · 주봉")
chart_name=st.selectbox("차트 종목",list(UNIVERSE))
tf=st.radio("차트 종류",["일봉","주봉","3분봉","5분봉"],horizontal=True)
if st.button("차트 불러오기"):
 symbol=UNIVERSE[chart_name]
 try:
  if tf in ("일봉","주봉"):
   d=prices(symbol,"1d","1y")
   if tf=="주봉":
    d=(d.set_index("time").resample("W-FRI")
       .agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
       .dropna(subset=["open","close"]).reset_index())
  elif tf=="5분봉":
   d=prices(symbol,"5m","1mo")
  else:
   d=prices(symbol,"1m","5d")
   d=(d.set_index("time").resample("3min")
      .agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
      .dropna(subset=["open","close"]).reset_index())
  st.caption(f"마지막 데이터: {d.time.iloc[-1]} | {len(d)}개 봉 | 제공처: Yahoo Finance")
  plot_candles(d,f"{chart_name} · {tf}")
 except Exception as e:
  st.error(f"차트 조회 실패: {type(e).__name__}: {e}")
  st.info("데이터 제공처 접속/조회 제한 또는 분봉 제공 기간 문제일 수 있습니다. 잠시 후 다시 시도하거나 일봉을 확인하세요.")

st.caption("분봉 시세는 실시간 보장되지 않습니다. 재무 데이터, 신호 및 가격은 거래소 공식 주문 데이터가 아닙니다.")
