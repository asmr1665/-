"""Daily watchlist and completed five-minute bar confirmation."""
import numpy as np
import pandas as pd

MARKETS = {"KOSPI": "KS", "KOSDAQ": "KQ"}
REQUIRED = ["date", "code", "name", "market", "close", "volume"]


def read_daily(source):
    frame = pd.read_csv(source, dtype={"code": str})
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError("필수 열 누락: " + ", ".join(sorted(missing)))
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    for column in ("open", "high", "low", "close", "volume", "value",
                   "foreign_net", "institution_net"):
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=REQUIRED)
    frame = frame[
        frame.market.isin(MARKETS) & frame.code.str.fullmatch(r"[0-9]{6}")
        & frame.close.gt(0) & frame.volume.ge(0)
    ]
    if frame.empty:
        raise ValueError("유효한 코스피·코스닥 일봉이 없습니다.")
    return frame.drop_duplicates(["market", "code", "date"], keep="last").sort_values("date")


def rank(frame):
    """Use only the latest market session and rows available through that session."""
    latest = frame.date.max()
    rows = []
    for (market, code), history in frame.groupby(["market", "code"], sort=False):
        if len(history) < 61 or history.date.iat[-1] != latest:
            continue
        close, volume = history.close, history.volume
        price = close.iat[-1]
        baseline = volume.iloc[-25:-5].mean()
        if baseline <= 0 or volume.iat[-1] <= 0:
            continue
        average_value = history.value.fillna(close * volume).tail(20).mean()
        top = history.high.fillna(close).tail(20).max()
        base = history.low.fillna(close).tail(20).min()
        weekly_range = close.tail(5).max() / close.tail(5).min() - 1
        prior_range = close.iloc[-25:-5].max() / close.iloc[-25:-5].min() - 1
        weekly_return = price / close.iat[-6] - 1
        monthly_return = price / close.iat[-21] - 1
        volume_ratio = volume.tail(5).mean() / baseline
        foreign = history.foreign_net.tail(5).sum(min_count=5)
        institution = history.institution_net.tail(5).sum(min_count=5)
        trend = price >= close.tail(20).mean() >= close.tail(60).mean()
        distance = 1 - price / top
        compression = weekly_range <= .065 and weekly_range <= prior_range * .8
        quiet = volume_ratio <= .9
        near_top = 0 <= distance <= .05
        eligible = (
            trend and near_top and compression and average_value >= 1e9
            and -.04 <= weekly_return <= .09 and monthly_return <= .22
        )
        support = history.low.fillna(close).tail(5).min()
        risk = top - support
        stop = support if 0 < risk / top <= .06 else np.nan
        target = top + 2 * risk if pd.notna(stop) else np.nan
        rows.append(dict(
            market=market, code=code, name=history.name.iat[-1], close=price,
            ret20=monthly_return, ret5=weekly_return, volume_ratio=volume_ratio,
            top=top, support=support, stop=stop, target=target,
            measured_high=history.high.tail(20).notna().all(),
            foreign=foreign, institution=institution, eligible=eligible,
            reasons=" · ".join(label for active, label in (
                (compression, "가격 변동폭 축소"), (quiet, "거래량 수축"),
                (near_top, "20일 상단 접근"), (trend, "중기 추세 유지"),
                (foreign > 0, "외국인 순매수"), (institution > 0, "기관 순매수"),
            ) if active),
            score=25 * trend + 25 * compression + 15 * quiet + 15 * near_top
                  + 5 * (foreign > 0) + 5 * (institution > 0),
        ))
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    benchmark = result.groupby("market").ret20.transform("median")
    result["relative"] = result.ret20 - benchmark
    result["score"] += result.relative.ge(0) * 10
    return result.sort_values(["score", "relative", "code"], ascending=[False, False, True])


def confirm(bars, row, now):
    """Compare cumulative volume with the same completed bar in prior sessions."""
    top = row["top"]
    today = bars[bars.index.date == now.date()]
    if today.empty:
        return "당일 시세 없음", None
    last = today.index[-1]
    clock = last.time()
    prior = bars[(bars.index.date < now.date()) & (bars.index.time <= clock)]
    prior_days = prior.groupby(prior.index.date)
    history = [
        day.Volume.sum() for _, day in prior_days
        if day.index[-1].time() == clock and len(day) == len(today)
        and day.index[0].time() == today.index[0].time()
    ]
    baseline = np.median(history[-5:]) if len(history) >= 3 else 0
    ratio = float(today.Volume.sum() / baseline) if baseline > 0 else None
    if not pd.notna(row["stop"]) or not row["measured_high"]:
        return "관찰 · 검증된 가격 범위 부족", ratio
    if (now - last - pd.Timedelta(minutes=5)).total_seconds() > 20 * 60:
        return "시세 갱신 지연 · 판단 보류", ratio
    if today.Open.iat[0] >= row["close"] * 1.04 or today.Close.iat[-1] >= top * 1.03:
        return "취소 · 시초 급등 또는 상단 3% 초과", ratio
    if today.Low.min() <= row["stop"]:
        return "취소 · 지지선 이탈", ratio
    if len(today) < 2 or (today.Close.tail(2) < top).any():
        return "관찰 · 상단 돌파 유지 대기", ratio
    if ratio is None or ratio < 1.5:
        return "관찰 · 같은 시간대 거래량 확인 대기", ratio
    return "매수 검토", ratio
