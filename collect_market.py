"""KRX 일봉과 투자자 수급 수집. 데이터 소스의 접근 제한 시 명시적으로 실패."""
import os, sys, time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from pykrx import stock

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"market_daily.csv"
today=datetime.now(ZoneInfo("Asia/Seoul")).date()
end=(today-timedelta(days=1)).strftime("%Y%m%d")
start=(today-timedelta(days=160)).strftime("%Y%m%d")
frames=[]
for market in ("KOSPI","KOSDAQ"):
    codes=stock.get_market_ticker_list(end, market=market)
    if not codes:
        raise RuntimeError(f"{market} 종목 목록 수집 실패")
    for idx,code in enumerate(codes):
        try:
            ohlcv=stock.get_market_ohlcv(start,end,code)
            investor=stock.get_market_trading_volume_by_date(start,end,code)
            if ohlcv.empty or investor.empty: continue
            ohlcv=ohlcv.rename(columns={"종가":"close","거래량":"volume"})
            needed=["close","volume"]
            if any(x not in ohlcv for x in needed): continue
            # pykrx 투자자별 매매동향: 외국인합계, 기관합계 columns
            if "외국인합계" not in investor or "기관합계" not in investor:
                continue
            joined=ohlcv[needed].join(investor[["외국인합계","기관합계"]],how="inner")
            joined=joined.rename(columns={"외국인합계":"foreign_net","기관합계":"institution_net"})
            joined["date"]=joined.index
            joined["code"]=code
            joined["name"]=stock.get_market_ticker_name(code)
            joined["market"]=market
            frames.append(joined.reset_index(drop=True))
        except Exception as e:
            print(f"수집 실패 {code}: {e}",file=sys.stderr)
        if (idx+1)%100==0: print(market,idx+1,len(codes),flush=True)
        time.sleep(.05)
if not frames: raise RuntimeError("수집 성공 종목 없음")
result=pd.concat(frames,ignore_index=True)
last=result.date.max()
covered=result[result.date==last].code.nunique()
if covered<1500:
    raise RuntimeError(f"최신 거래일 수집 종목 {covered}개로 불완전. 기존 파일 유지")
tmp=OUT.with_suffix(".tmp")
result.to_csv(tmp,index=False,encoding="utf-8-sig")
os.replace(tmp,OUT)
print(f"저장 완료: {covered}종목 / {last}")
