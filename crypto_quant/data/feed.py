from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Iterator

'''
BarData  = 一根 K 线
DataLine = 某一个字段组成的一条线，比如所有 close,volume
DataFeed = 多根 K 线组成的数据源，里面包含 open/high/low/close/volume 多条线
'''
@dataclass(frozen=True, slots=True) #不允许被修改和限制字段；
class BarData: #单根k线类
    symbol: str #交易对名称
    timeframe: str #k线周期
    datetime: datetime #时间（datetime格式）
    open: Decimal #开盘价
    high: Decimal #最高价
    low: Decimal #最低价
    close: Decimal #收盘价
    volume: Decimal #成交量


class DataLine: #“数据线”类
    def __init__(self, values: list[Decimal | datetime | str] | None = None):
        self._values = values or []
        self._cursor = -1 #初始值为负一，创建 DataLine 时，回测还没开始，当前没有任何 K 线。

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def values(self) -> list[Decimal | datetime | str]:
        return list(self._values)

    def append(self, value: Decimal | datetime | str) -> None:
        self._values.append(value) #向数据线末尾追加一个值

    def advance(self, cursor: int) -> None: #告诉这条数据线：当前走到第几根 K 线。
        self._cursor = cursor #通过 _cursor 表示当前回测走到第几根 K 线,比如当前 _cursor = 1，表示当前走到第 1 根 K 线。

    def reset(self) -> None:
        self._cursor = -1

    def window(self, size: int) -> list[Decimal | datetime | str]:
        if size <= 0:
            raise ValueError("window size must be positive")
        start = self._cursor - size + 1
        if start < 0 or self._cursor < 0:
            raise IndexError("data line window out of range")
        return self._values[start : self._cursor + 1]

    def __getitem__(self, offset: int) -> Decimal | datetime | str: #offset就是data.close[0]里的0或data.close[-1]里的-1。
        index = self._cursor + offset #offset 不是绝对位置，而是相对于当前 K 线的位置（-1、0、1），所以真实索引要算index = self._cursor + offset；
        if index < 0 or index >= len(self._values): #越界检查
            raise IndexError("data line offset out of range")
        return self._values[index]

    def __len__(self) -> int: #返回这条线总共有多少个值，例如len(data.close)
        return len(self._values)


class DataFeed:  #“数据线源类”，DataFeed 是多根 K 线组成的数据源，它里面不仅保存原始 K 线列表（self.bars）,还拆分出了很多条数据线；
    def __init__(self, bars: Iterable[BarData]): #这里的 bars 可以是任何可迭代的 K 线集合。
        self.bars = list(bars)
        self.datetime = DataLine([bar.datetime for bar in self.bars])
        self.open = DataLine([bar.open for bar in self.bars])
        self.high = DataLine([bar.high for bar in self.bars])
        self.low = DataLine([bar.low for bar in self.bars])
        self.close = DataLine([bar.close for bar in self.bars])
        self.volume = DataLine([bar.volume for bar in self.bars])
        self._cursor = -1 #表示整个数据源当前走到哪根 K 线，和 DataLine._cursor 类似，初始为 -1，表示还没开始。

    @property
    def current(self) -> BarData: #表示当前k线，比如data.current，返回self.bars[2]，也就是第 2 根 K 线。
        if self._cursor < 0:
            raise RuntimeError("data feed has not started")
        return self.bars[self._cursor]

    def __iter__(self) -> Iterator[BarData]:
        for cursor, bar in enumerate(self.bars): #enumerate 会同时给出索引 cursor，当前 K 线 bar，这是detafeed的核心。
            self._cursor = cursor #自己更新，表示整个数据源当前走到第几根 K 线。
            for line in [self.datetime, self.open, self.high, self.low, self.close, self.volume]: #它会让所有数据线同步推进到当前 K 线
                line.advance(cursor)
            yield bar #把当前这根 K 线交出去，所以在回测引擎里每一轮拿到的就是当前 K 线。

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def available_bars(self) -> int:
        return max(self._cursor + 1, 0)

    def reset(self) -> None:
        self._cursor = -1
        for line in [self.datetime, self.open, self.high, self.low, self.close, self.volume]:
            line.reset()

    def window(self, size: int) -> list[BarData]:
        if size <= 0:
            raise ValueError("window size must be positive")
        start = self._cursor - size + 1
        if start < 0 or self._cursor < 0:
            raise IndexError("data feed window out of range")
        return self.bars[start : self._cursor + 1]

    def slice(self, start: int | None = None, end: int | None = None) -> "DataFeed":
        return DataFeed(self.bars[start:end])

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "symbol": bar.symbol,
                    "timeframe": bar.timeframe,
                    "datetime": bar.datetime,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in self.bars
            ]
        )

    def __len__(self) -> int:
        return len(self.bars)
