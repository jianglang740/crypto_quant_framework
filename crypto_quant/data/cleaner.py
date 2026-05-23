from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from crypto_quant.data.feed import BarData
from crypto_quant.data.time_utils import BEIJING_TIMEZONE, normalize_datetime, timestamp_to_datetime


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
}


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    input_count: int
    output_count: int
    duplicate_count: int
    missing_intervals: list[tuple[datetime, datetime]]


def timeframe_to_timedelta(timeframe: str) -> timedelta | None:
    seconds = _TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None:
        return None
    return timedelta(seconds=seconds)


def parse_bar_datetime(
    value: datetime | int | float | Decimal,
    source_timezone: timezone = BEIJING_TIMEZONE,
    target_timezone: timezone = BEIJING_TIMEZONE,
    drop_timezone: bool = False,
) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=source_timezone)
        converted = value.astimezone(target_timezone)
        if drop_timezone:
            return converted.replace(tzinfo=None)
        return converted
    return timestamp_to_datetime(value, target_timezone=target_timezone, drop_timezone=drop_timezone)


def clean_bars(
    bars: list[BarData],
    target_timezone: timezone = BEIJING_TIMEZONE,
    drop_timezone: bool = False,
    allow_duplicate: bool = False,
) -> list[BarData]:
    cleaned: dict[tuple[str, str, datetime], BarData] = {}
    for bar in bars:
        _validate_ohlcv(bar)
        bar_datetime = normalize_datetime(bar.datetime, target_timezone=target_timezone, drop_timezone=drop_timezone)
        normalized_bar = BarData(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            datetime=bar_datetime,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        key = (normalized_bar.symbol, normalized_bar.timeframe, normalized_bar.datetime)
        if key in cleaned and not allow_duplicate:
            continue
        cleaned[key] = normalized_bar
    return sorted(cleaned.values(), key=lambda item: (item.symbol, item.timeframe, item.datetime))


def validate_bars(
    bars: list[BarData],
    expected_timeframe: str | None = None,
    raise_on_missing: bool = False,
) -> DataQualityReport:
    sorted_bars = sorted(bars, key=lambda item: (item.symbol, item.timeframe, item.datetime))
    seen: set[tuple[str, str, datetime]] = set()
    duplicate_count = 0
    missing_intervals: list[tuple[datetime, datetime]] = []
    previous: BarData | None = None
    for bar in sorted_bars:
        _validate_ohlcv(bar)
        if expected_timeframe is not None and bar.timeframe != expected_timeframe:
            raise ValueError(f"unexpected timeframe: {bar.timeframe}")
        key = (bar.symbol, bar.timeframe, bar.datetime)
        if key in seen:
            duplicate_count += 1
        seen.add(key)
        if previous is not None and previous.symbol == bar.symbol and previous.timeframe == bar.timeframe:
            expected_delta = timeframe_to_timedelta(bar.timeframe)
            if expected_delta is not None and bar.datetime - previous.datetime != expected_delta:
                missing_intervals.append((previous.datetime, bar.datetime))
        previous = bar
    if duplicate_count:
        raise ValueError(f"bars contain duplicated datetime rows: {duplicate_count}")
    if missing_intervals and raise_on_missing:
        raise ValueError(f"bars contain missing intervals: {missing_intervals[:10]}")
    return DataQualityReport(
        input_count=len(bars),
        output_count=len(sorted_bars),
        duplicate_count=duplicate_count,
        missing_intervals=missing_intervals,
    )


def clean_and_validate_bars(
    bars: list[BarData],
    target_timezone: timezone = BEIJING_TIMEZONE,
    drop_timezone: bool = False,
    expected_timeframe: str | None = None,
    raise_on_missing: bool = False,
) -> tuple[list[BarData], DataQualityReport]:
    cleaned = clean_bars(bars, target_timezone=target_timezone, drop_timezone=drop_timezone)
    report = validate_bars(cleaned, expected_timeframe=expected_timeframe, raise_on_missing=raise_on_missing)
    return cleaned, DataQualityReport(
        input_count=len(bars),
        output_count=len(cleaned),
        duplicate_count=len(bars) - len(cleaned),
        missing_intervals=report.missing_intervals,
    )


def _validate_ohlcv(bar: BarData) -> None:
    values = [bar.open, bar.high, bar.low, bar.close, bar.volume]
    if any(value.is_nan() or value.is_infinite() for value in values):
        raise ValueError(f"bar contains invalid numeric value: {bar}")
    if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
        raise ValueError(f"bar contains non-positive OHLC value: {bar}")
    if bar.volume < 0:
        raise ValueError(f"bar contains negative volume: {bar}")
    if bar.high < bar.low:
        raise ValueError(f"bar high is lower than low: {bar}")
    if bar.open > bar.high or bar.open < bar.low or bar.close > bar.high or bar.close < bar.low:
        raise ValueError(f"bar OHLC is inconsistent: {bar}")
