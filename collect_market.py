"""Collect KRX daily history. Publish only when both markets pass coverage checks."""
import os
import sys
import tempfile
import time
from datetime import datetime, time as clock, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pykrx import stock

OUT = Path(__file__).with_name("market_daily.csv")
PRICE = {"시가": "open", "고가": "high", "저가": "low", "종가": "close",
         "거래량": "volume", "거래대금": "value"}
FLOW = {"외국인합계": "foreign_net", "기관합계": "institution_net"}


def collect():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    cutoff = now.date() - timedelta(days=now.time() < clock(18, 30))
    end = stock.get_nearest_business_day_in_a_week(date=cutoff.strftime("%Y%m%d"))
    start = (cutoff - timedelta(days=210)).strftime("%Y%m%d")
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        names = stock.get_market_ticker_list(end, market=market)
        if not names:
            raise RuntimeError(f"{market} 종목 목록 수집 실패")
        market_frames = []
        for index, code in enumerate(names, start=1):
            try:
                bars = stock.get_market_ohlcv(start, end, code, adjusted=False)
                if bars.empty or not {"종가", "거래량"} <= set(bars):
                    continue
                bars = bars.rename(columns=PRICE).reindex(columns=PRICE.values())
                if bars.index.max().strftime("%Y%m%d") != end:
                    continue
                try:
                    flows = stock.get_market_trading_volume_by_date(start, end, code)
                    flows = flows.rename(columns=FLOW).reindex(columns=FLOW.values())
                    bars = bars.join(flows)
                except Exception as error:
                    print(f"수급 {code}: {type(error).__name__}", file=sys.stderr)
                bars = bars.assign(date=bars.index, code=code, market=market,
                                   name=stock.get_market_ticker_name(code) or code)
                market_frames.append(bars.reset_index(drop=True))
            except Exception as error:
                print(f"일봉 {code}: {type(error).__name__}", file=sys.stderr)
            finally:
                time.sleep(.05)
                if index % 100 == 0:
                    print(market, index, len(names), flush=True)
        if len(market_frames) / len(names) < .90:
            raise RuntimeError(f"{market} 수집 {len(market_frames)}/{len(names)} · 기존 파일 유지")
        frames.extend(market_frames)
    with tempfile.NamedTemporaryFile(dir=OUT.parent, suffix=".tmp", delete=False) as handle:
        temp = Path(handle.name)
    try:
        pd.concat(frames, ignore_index=True).to_csv(temp, index=False, encoding="utf-8-sig")
        os.replace(temp, OUT)
    finally:
        temp.unlink(missing_ok=True)
    print(f"저장 완료 · {end} · {len(frames):,}종목")


if __name__ == "__main__":
    collect()
