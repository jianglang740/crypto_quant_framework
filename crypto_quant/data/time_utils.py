from datetime import datetime, timedelta, timezone
from decimal import Decimal

BEIJING_TIMEZONE = timezone(timedelta(hours=8))
UTC_TIMEZONE = timezone.utc


def normalize_datetime(value: datetime, target_timezone: timezone = UTC_TIMEZONE, drop_timezone: bool = False) -> datetime:
    if value.tzinfo is None:
        converted = value.replace(tzinfo=target_timezone)
    else:
        converted = value.astimezone(target_timezone)
    if drop_timezone:
        return converted.replace(tzinfo=None)
    return converted


def timestamp_to_datetime(timestamp: int | float | Decimal, target_timezone: timezone = UTC_TIMEZONE, drop_timezone: bool = False) -> datetime:
    numeric_timestamp = float(timestamp)
    if numeric_timestamp > 10_000_000_000:
        numeric_timestamp = numeric_timestamp / 1000
    value = datetime.fromtimestamp(numeric_timestamp, tz=UTC_TIMEZONE).astimezone(target_timezone)
    if drop_timezone:
        return value.replace(tzinfo=None)
    return value


def datetime_to_milliseconds(value: datetime, source_timezone: timezone = BEIJING_TIMEZONE) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=source_timezone)
    return int(value.astimezone(UTC_TIMEZONE).timestamp() * 1000)


def to_milliseconds(value: datetime | int | float | Decimal | None, source_timezone: timezone = BEIJING_TIMEZONE) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return datetime_to_milliseconds(value, source_timezone=source_timezone)
    numeric_value = float(value)
    if numeric_value > 10_000_000_000:
        return int(numeric_value)
    return int(numeric_value * 1000)
