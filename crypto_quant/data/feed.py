from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Iterator


@dataclass(frozen=True, slots=True)
class BarData:
    symbol: str
    timeframe: str
    datetime: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class DataLine:
    def __init__(self, values: list[Decimal | datetime | str] | None = None):
        self._values = values or []
        self._cursor = -1

    def append(self, value: Decimal | datetime | str) -> None:
        self._values.append(value)

    def advance(self, cursor: int) -> None:
        self._cursor = cursor

    def __getitem__(self, offset: int) -> Decimal | datetime | str:
        index = self._cursor + offset
        if index < 0 or index >= len(self._values):
            raise IndexError("data line offset out of range")
        return self._values[index]

    def __len__(self) -> int:
        return len(self._values)


class DataFeed:
    def __init__(self, bars: Iterable[BarData]):
        self.bars = list(bars)
        self.datetime = DataLine([bar.datetime for bar in self.bars])
        self.open = DataLine([bar.open for bar in self.bars])
        self.high = DataLine([bar.high for bar in self.bars])
        self.low = DataLine([bar.low for bar in self.bars])
        self.close = DataLine([bar.close for bar in self.bars])
        self.volume = DataLine([bar.volume for bar in self.bars])
        self._cursor = -1

    @property
    def current(self) -> BarData:
        if self._cursor < 0:
            raise RuntimeError("data feed has not started")
        return self.bars[self._cursor]

    def __iter__(self) -> Iterator[BarData]:
        for cursor, bar in enumerate(self.bars):
            self._cursor = cursor
            for line in [self.datetime, self.open, self.high, self.low, self.close, self.volume]:
                line.advance(cursor)
            yield bar

    def __len__(self) -> int:
        return len(self.bars)
