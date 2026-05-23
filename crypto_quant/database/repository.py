# ！！！ repository.py 是“业务对象”和“MySQL 表”之间的翻译层。

'''
第一部分：import 和辅助函数
第二部分：MarketDataRepository
第三部分：TradingRepository 的查询方法
第四部分：TradingRepository 的写入方法
第五部分：save_backtest_result
第六部分：save_live_snapshot
'''
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select #导入查询功能
from sqlalchemy.dialects.mysql import insert #导入插入功能
from sqlalchemy.orm import Session

from crypto_quant.data.feed import BarData, DataFeed
from crypto_quant.database.models import (
    AccountSnapshot,
    EquityCurve,
    Kline,
    OrderRecord,
    PositionSnapshot,
    StrategyRun,
    TradeRecord,
) #导入models里已经定义好的数据表
from crypto_quant.strategy.base import Account, LocalOrder, Position, StrategyBase, Trade #导入策略基类


#MarketDataRepository 负责行情数据的入库和读出：upsert_klines 把 BarData 写进 klines 表，get_klines 从 klines 表读出 Kline ORM 对象，get_data_feed 再把 Kline 转成回测引擎可用的 DataFeed

class MarketDataRepository: #负责行情数据在 Python 对象和 MySQL klines 表之间来回转换。
    def __init__(self, session: Session):#MarketDataRepository 不自己连接数据库，它需要外部传进来一个 Session
        self.session = session #这个 repository 后续所有数据库操作，都用这次 session 完成
    '''
    把一组 BarData 写入 MySQL 的 klines 表
    如果已经存在同一根 K 线，就更新它
    '''
    def upsert_klines(self, bars: list[BarData], exchange: str = "binance") -> None:
        for bar in bars: #一根一根 K 线写入数据库
            statement = insert(Kline).values( #对应Kline类，像klines表中插入数据
                exchange=exchange,
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                open_time=bar.datetime.replace(tzinfo=None),#入库时统一去掉时区，避免 MySQL 和 SQLAlchemy 处理 timezone-aware datetime 时出问题
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            '''
            如果插入时发现这根 K 线已经存在，
            就更新 open/high/low/close/volume
            '''
            update_columns = { #exchange + symbol + timeframe + open_time已经构成了k线的唯一身份
                "open": statement.inserted.open,
                "high": statement.inserted.high,
                "low": statement.inserted.low,
                "close": statement.inserted.close,
                "volume": statement.inserted.volume,
            }
            self.session.execute(statement.on_duplicate_key_update(**update_columns))
        self.session.commit() #循环结束后统一提交事务

    def get_klines( 
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        exchange: str = "binance",
        limit: int | None = None,
    ) -> list[Kline]: #从 MySQL 的 klines 表查询 K 线，返回 Kline ORM 对象列表
        
        '''
        SELECT *
        FROM klines
        WHERE exchange = 'binance'
        AND symbol = 'BTC/USDT'
        AND timeframe = '1m'
        ORDER BY open_time ASC;
        '''

        statement: Select[tuple[Kline]] = ( #构造查询语句
            select(Kline)
            .where(Kline.exchange == exchange)
            .where(Kline.symbol == symbol)
            .where(Kline.timeframe == timeframe)
            .order_by(Kline.open_time.asc()) #按开盘时间升序排序,回测喂数据要按顺序不能乱喂
        )
        if start is not None:
            statement = statement.where(Kline.open_time >= start.replace(tzinfo=None)) #如果传了start，就只查open_time >= start，也就是从某个时间开始
        if end is not None:
            statement = statement.where(Kline.open_time <= end.replace(tzinfo=None)) #如果传了end，就只查open_time <= end，也就是查到某个时间为止
        if limit is not None:
            statement = statement.limit(limit) #如果传了limit，限制最多返回多少根 K 线
        return list(self.session.scalars(statement).all()) #执行SQL，并把结果取出来

    def get_data_feed(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        exchange: str = "binance",
        limit: int | None = None,
    ) -> DataFeed: #从 MySQL 读取 K 线，并转换成框架回测可用的 DataFeed，比get_klines更进一步
        klines = self.get_klines( #先调用 get_klines，也就是说get_data_feed本身不写查询逻辑，而是复用get_klines
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
            limit=limit,
        )
        '''
        映射：
        Kline.symbol     -> BarData.symbol
        Kline.timeframe  -> BarData.timeframe
        Kline.open_time  -> BarData.datetime #注意这里再次体现数据库里叫 open_time，程序里叫 datetime
        Kline.open       -> BarData.open
        Kline.high       -> BarData.high
        Kline.low        -> BarData.low
        Kline.close      -> BarData.close
        Kline.volume     -> BarData.volume
        '''
        return DataFeed( #返回datafeed
            [
                BarData(
                    symbol=kline.symbol,
                    timeframe=kline.timeframe,
                    datetime=kline.open_time,
                    open=kline.open,
                    high=kline.high,
                    low=kline.low,
                    close=kline.close,
                    volume=kline.volume,
                )
                for kline in klines #遍历klines里的k线数据
            ]
        )
        '''
        get_klines：偏数据库层
        get_data_feed：偏框架业务层
        '''


'''
TradingRepository
= 交易/回测/实盘结果的数据库仓库
= 负责 strategy_runs / orders / trades / equity_curve / account_snapshots / position_snapshots 这些表的读写

1. 初始化
   __init__

2. 运行记录 strategy_runs
   create_run
   finish_run
   get_run
   list_runs

3. 查询结果
   get_orders
   get_trades
   get_equity_curve
   get_account_snapshots
   get_position_snapshots

4. 保存订单 orders
   save_order
   save_local_order
   upsert_local_order
   update_order_status

5. 保存成交 trades
   save_trade
   save_framework_trade

6. 保存权益/账户/持仓
   save_equity
   save_equity_point
   save_account_snapshot
   save_position_snapshot

7. 高级封装方法
   save_live_snapshot
   save_backtest_result

8. 私有辅助方法
   _save_result_orders
   _save_result_trades
   _local_order_raw
   _trade_to_dict
'''
class TradingRepository:
    def __init__(self, session: Session):
        self.session = session
#=====================运行记录=========================
    def create_run(
        self,
        name: str,
        run_type: str,
        trading_mode: str,
        strategy_name: str | None = None,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        initial_cash: Decimal | None = None,
        config: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> StrategyRun: #创建一次策略运行记录,也就是往StrategyRun里插入一行数据
        run = StrategyRun( #创建 StrategyRun ORM 对象
            run_id=run_id or str(uuid4()),
            name=name,
            run_type=run_type,
            trading_mode=trading_mode,
            strategy_name=strategy_name,
            symbols=json.dumps(symbols, ensure_ascii=False) if symbols is not None else None,
            timeframe=timeframe,
            initial_cash=initial_cash,
            status="running",
            config=json.dumps(config, ensure_ascii=False, default=str) if config is not None else None,
        )
        self.session.add(run) #把这个 StrategyRun ORM 对象加入当前数据库会话
        self.session.commit() #正式提交，这一步之后，MySQL 里真的新增一行
        self.session.refresh(run) #从数据库重新刷新 run 对象，获取一些数据库或 SQLAlchemy 自动生成的字段对应的数据，如自主主键ID
        return run #返回这个 StrategyRun 对象
        '''
        所以调用方法可以得到：
        run.run_id
        run.id
        run.status
        run.created_at
        '''

    def finish_run(self, run_id: str, final_equity: Decimal | None = None, status: str = "finished") -> StrategyRun: #结束一次运行记录，也就是更新strategy_runs里的某一行
        run = self.get_run(run_id) #根据run_id找到对应的StrategyRun
        if run is None:
            raise ValueError(f"unknown run_id: {run_id}") #找不到就报错，如果数据库里没有这个 run_id，就不能结束它，这是合理的，因为不能结束一个不存在的运行
        #更新结束字段
        run.ended_at = datetime.utcnow() #结束时间
        run.final_equity = final_equity #最终权益
        run.status = status #最终运行状态
        self.session.commit()
        self.session.refresh(run) #刷新
        return run

    def get_run(self, run_id: str) -> StrategyRun | None:
        return self.session.scalar(select(StrategyRun).where(StrategyRun.run_id == run_id)) #根据 run_id 查询一条 strategy_runs 记录

    def list_runs(
        self,
        run_type: str | None = None,
        strategy_name: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[StrategyRun]: #查询多条运行记录，也就是查strategy_runs表
        statement: Select[tuple[StrategyRun]] = select(StrategyRun).order_by(StrategyRun.created_at.desc()) #按创建时间倒序，最新的在前面
        if run_type is not None:
            statement = statement.where(StrategyRun.run_type == run_type)
        if strategy_name is not None:
            statement = statement.where(StrategyRun.strategy_name == strategy_name)
        if status is not None:
            statement = statement.where(StrategyRun.status == status)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement).all()) #执行查询并返回list[StrategyRun]
    
#===================查询结果===========================
    '''
    根据 run_id，从某张明细表里查出属于某一次运行的数据
    它们都不写数据库，只读数据库，所以都没有session.commit(),因为查询不需要提交事务

    get_orders             -> 查 orders 表
    get_trades             -> 查 trades 表
    get_equity_curve       -> 查 equity_curve 表
    get_account_snapshots  -> 查 account_snapshots 表
    get_position_snapshots -> 查 position_snapshots 表

    1. 先 select(某个 ORM 类)
    2. where(run_id == run_id)
    3. order_by(时间字段升序)
    4. 根据可选条件继续 where
    5. session.scalars(statement).all()
    6. 转成 list 返回

    run_id 是主线
    时间排序是复盘用的
    '''
    def get_orders(
        self,
        run_id: str,
        strategy_name: str | None = None,
        status: str | None = None,
    ) -> list[OrderRecord]: #返回OrderRecord表的列表形式
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(OrderRecord.run_id == run_id).order_by(OrderRecord.created_at.asc()) #按run_id查询与按订单记录创建时间升序
        #按不同的规则筛选
        if strategy_name is not None:
            statement = statement.where(OrderRecord.strategy_name == strategy_name)
        if status is not None:
            statement = statement.where(OrderRecord.status == status)
        return list(self.session.scalars(statement).all()) #返回结果列表

    def get_trades(self, run_id: str, strategy_name: str | None = None) -> list[TradeRecord]: #返回TradeRecord表的列表形式
        statement: Select[tuple[TradeRecord]] = select(TradeRecord).where(TradeRecord.run_id == run_id).order_by(TradeRecord.traded_at.asc()) #按run_id查询与按订单成交时间升序
        #按策略名称查询
        if strategy_name is not None:
            statement = statement.where(TradeRecord.strategy_name == strategy_name)
        return list(self.session.scalars(statement).all()) #返回结果列表

    def get_equity_curve(self, run_id: str, strategy_name: str | None = None) -> list[EquityCurve]: #返回EquityCurve表的列表形式
        statement: Select[tuple[EquityCurve]] = select(EquityCurve).where(EquityCurve.run_id == run_id).order_by(EquityCurve.timestamp.asc()) #按run_id查询与按时间戳升序
        #按策略名称查询
        if strategy_name is not None:
            statement = statement.where(EquityCurve.strategy_name == strategy_name)
        return list(self.session.scalars(statement).all()) #返回结果列表

    def get_account_snapshots(self, run_id: str) -> list[AccountSnapshot]: #返回AccountSnapshot表的列表形式
        statement: Select[tuple[AccountSnapshot]] = select(AccountSnapshot).where(AccountSnapshot.run_id == run_id).order_by(AccountSnapshot.timestamp.asc()) #按run_id查询与按时间戳升序
        return list(self.session.scalars(statement).all()) #返回结果列表

    def get_position_snapshots(
        self,
        run_id: str,
        strategy_name: str | None = None,
        symbol: str | None = None,
    ) -> list[PositionSnapshot]: #返回PositionSnapshot表的列表形式
        statement: Select[tuple[PositionSnapshot]] = select(PositionSnapshot).where(PositionSnapshot.run_id == run_id).order_by(PositionSnapshot.timestamp.asc())#按run_id查询与按时间戳升序
        #按不同的规则筛选
        if strategy_name is not None:
            statement = statement.where(PositionSnapshot.strategy_name == strategy_name)
        if symbol is not None:
            statement = statement.where(PositionSnapshot.symbol == symbol)
        return list(self.session.scalars(statement).all()) #返回结果列表

#==================保存订单=================================

    '''
    save_order
    保存“交易所/ccxt 风格的订单 dict”

    save_local_order
    保存“框架内部 LocalOrder 对象”

    upsert_local_order
    保存或更新“框架内部 LocalOrder 对象”

    update_order_status
    根据订单 ID 更新订单状态、成交数量、均价

    save_order：外部订单 dict -> orders 表
    save_local_order：框架内部订单对象 -> orders 表
    upsert_local_order：框架内部订单对象 -> orders 表，不重复插入
    update_order_status：更新 orders 表已有订单状态

    交易所 API / ccxt 订单 dict
        ↓
    save_order()
        ↓
     orders 表


    框架内部 LocalOrder
        ↓
    save_local_order()
        ↓
     orders 表新增一行


    框架内部 LocalOrder
        ↓
    upsert_local_order()
        ↓
    不存在：save_local_order()
    已存在：更新原订单行


    订单 ID + 新状态
        ↓
    update_order_status()
        ↓
    更新 orders 表已有记录
    '''

    def save_order(self, order: dict[str, Any], trading_mode: str, run_id: str | None = None, strategy_name: str | None = None) -> OrderRecord: #保存一个订单字典到 orders 表
        #这个order通常像交易所API或ccxt 返回的订单结构,也就是说它处理的是dict 格式订单，不是框架内部的LocalOrder
        record = OrderRecord(
            run_id=run_id,
            strategy_name=strategy_name,
            exchange_order_id=str(order.get("id")) if order.get("id") is not None else None,
            client_order_id=str(order.get("clientOrderId")) if order.get("clientOrderId") is not None else None,
            symbol=order["symbol"],
            trading_mode=trading_mode,
            side=order["side"],
            order_type=order["type"],
            status=order.get("status", "open"),
            amount=Decimal(str(order.get("amount") or "0")),
            price=Decimal(str(order["price"])) if order.get("price") is not None else None,
            filled=Decimal(str(order.get("filled") or "0")),
            average=Decimal(str(order["average"])) if order.get("average") is not None else None,
            position_side=(order.get("info") or {}).get("positionSide"),
            reduce_only=bool(order.get("reduceOnly") or (order.get("info") or {}).get("reduceOnly") or False),
            time_in_force=order.get("timeInForce") or (order.get("info") or {}).get("timeInForce"),
            raw=json.dumps(order, ensure_ascii=False, default=str), #保存原始订单数据
        ) #订单 dict -> OrderRecord ORM 对象
        self.session.add(record) #把这个OrderRecord ORM对象加入当前数据库会话
        self.session.commit() #正式提交，这一步之后，MySQL 里真的新增一行
        self.session.refresh(record) #刷新数据库生成的字段
        return record #返回记录

    def save_local_order(
        self,
        order: LocalOrder,
        trading_mode: str,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange: str = "binance",
    ) -> OrderRecord: #保存框架内部的LocalOrder对象到orders表
        request = order.request #LocalOrder通常包含一个下单请求对象，request = order.request
        record = OrderRecord( #字段映射LocalOrder -> OrderRecord
            run_id=run_id,
            strategy_name=strategy_name,
            exchange=exchange,
            client_order_id=order.id,
            symbol=request.symbol,
            trading_mode=trading_mode,
            side=request.side.value,
            order_type=request.order_type.value,
            status=order.status.value,
            amount=request.amount,
            price=request.price,
            filled=order.filled,
            average=order.average,
            position_side=request.position_side.value if request.position_side is not None else None,
            reduce_only=request.reduce_only,
            time_in_force=request.time_in_force.value if request.time_in_force is not None else None,
            raw=self._local_order_raw(order),
            created_at=order.created_at.replace(tzinfo=None),
            updated_at=datetime.utcnow(),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def upsert_local_order(
        self,
        order: LocalOrder,
        trading_mode: str,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange: str = "binance",
    ) -> OrderRecord: #保存或更新框架内部订单，如果订单不存在 -> save_local_order 新增，如果订单已存在 -> 更新原记录
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(OrderRecord.client_order_id == order.id)
        if run_id is not None:
            statement = statement.where(OrderRecord.run_id == run_id)
        record = self.session.scalar(statement)
        if record is None:
            return self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name, exchange=exchange)
        request = order.request
        record.strategy_name = strategy_name
        record.exchange = exchange
        record.symbol = request.symbol
        record.trading_mode = trading_mode
        record.side = request.side.value
        record.order_type = request.order_type.value
        record.status = order.status.value
        record.amount = request.amount
        record.price = request.price
        record.filled = order.filled
        record.average = order.average
        record.position_side = request.position_side.value if request.position_side is not None else None
        record.reduce_only = request.reduce_only
        record.time_in_force = request.time_in_force.value if request.time_in_force is not None else None
        record.raw = self._local_order_raw(order)
        record.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_order_status(
        self,
        order_id: str,
        status: str,
        run_id: str | None = None,
        filled: Decimal | None = None,
        average: Decimal | None = None,
    ) -> OrderRecord: #根据订单 ID 更新某条订单的状态
        statement: Select[tuple[OrderRecord]] = select(OrderRecord).where(
            (OrderRecord.client_order_id == order_id) | (OrderRecord.exchange_order_id == order_id)
        )
        if run_id is not None:
            statement = statement.where(OrderRecord.run_id == run_id)
        record = self.session.scalar(statement)
        if record is None:
            raise ValueError(f"unknown order_id: {order_id}")
        record.status = status
        if filled is not None:
            record.filled = filled
        if average is not None:
            record.average = average
        record.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(record)
        return record
    #这 4 个方法负责 orders 表的写入和更新：save_order 保存交易所订单 dict，save_local_order 保存框架内部订单，upsert_local_order 防止重复插入同一订单，update_order_status 用来更新已有订单状态。
#=========================保存成交=========================================

    '''
    save_trade
    输入已经是 TradeRecord
    直接保存

    save_framework_trade
    输入是框架内部 Trade 对象
    先转换成 TradeRecord
    再保存
    '''

    '''
    save_trade适用于：
    你已经自己构造好了 TradeRecord
    只想让 repository 帮你保存
    '''
    def save_trade(self, trade: TradeRecord) -> TradeRecord:
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade

    def save_framework_trade(
        self,
        trade: Trade,
        trading_mode: str | None = None,
        run_id: str | None = None,
        strategy_name: str | None = None,
        exchange_order_id: str | None = None,
        position_side: str | None = None,
        exchange: str = "binance",
    ) -> TradeRecord: #把框架内部的Trade对象保存到MySQL的trades 表
        record = TradeRecord(
            run_id=run_id,
            strategy_name=strategy_name,
            exchange=exchange,
            exchange_trade_id=trade.id,
            exchange_order_id=exchange_order_id,
            trading_mode=trading_mode,
            symbol=trade.symbol,
            side=trade.side.value,
            position_side=position_side,
            amount=trade.amount,
            price=trade.price,
            fee=trade.fee,
            traded_at=trade.traded_at.replace(tzinfo=None),
            raw=json.dumps(self._trade_to_dict(trade), ensure_ascii=False, default=str),
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
    #保存成交这一组负责把成交数据写入 trades 表；save_trade 直接保存 TradeRecord，save_framework_trade 把框架内部 Trade 转成 TradeRecord 后保存，是回测结果入库时最常用的成交保存方法。
    
#====================保存权益=================================
    '''
    save_equity
    输入已经是 EquityCurve ORM 对象
    直接保存

    save_equity_point
    输入是 timestamp + Account
    先转换成 EquityCurve
    再保存
    '''
    def save_equity(self, equity: EquityCurve) -> EquityCurve:
        self.session.add(equity)
        self.session.commit()
        self.session.refresh(equity)
        return equity
    
    def save_equity_point(
        self,
        timestamp: datetime,
        account: Account,
        strategy_name: str,
        run_id: str | None = None,
        trading_mode: str | None = None,
    ) -> EquityCurve: #保存某一个时间点的账户权益状态
        record = EquityCurve(
            run_id=run_id,
            strategy_name=strategy_name,
            trading_mode=trading_mode,
            timestamp=timestamp.replace(tzinfo=None),
            cash=account.cash,
            equity=account.equity,
            available=account.available,
            margin=account.margin,
            maintenance_margin=account.maintenance_margin,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
    #保存权益这一组负责写 equity_curve 表；save_equity 直接保存 EquityCurve ORM 对象，save_equity_point 把框架内部 Account 在某个 timestamp 的状态转换成 EquityCurve 保存，主要用于记录回测权益曲线。

    def save_account_snapshot(
        self,
        account: Account,
        run_id: str,
        trading_mode: str,
        timestamp: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> AccountSnapshot:
        record = AccountSnapshot(
            run_id=run_id,
            timestamp=(timestamp or datetime.utcnow()).replace(tzinfo=None),
            trading_mode=trading_mode,
            cash=account.cash,
            equity=account.equity,
            available=account.available,
            margin=account.margin,
            maintenance_margin=account.maintenance_margin,
            margin_ratio=account.margin_ratio,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            raw=json.dumps(raw, ensure_ascii=False, default=str) if raw is not None else None,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save_position_snapshot(
        self,
        position: Position,
        run_id: str,
        timestamp: datetime | None = None,
        strategy_name: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> PositionSnapshot:
        record = PositionSnapshot(
            run_id=run_id,
            strategy_name=strategy_name,
            timestamp=(timestamp or datetime.utcnow()).replace(tzinfo=None),
            symbol=position.symbol,
            side=position.side.value,
            amount=position.amount,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            margin=position.margin,
            liquidation_price=position.liquidation_price,
            unrealized_pnl=position.unrealized_pnl,
            raw=json.dumps(raw, ensure_ascii=False, default=str) if raw is not None else None,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

#==========================高级封装方法============================

    '''
    它们之所以叫“高级封装”，是因为它们不是只保存一张表，而是一次调用会联动保存多张表
    save_live_snapshot
    保存 live/dry_run 运行中的当前状态快照

    save_backtest_result
    保存一次完整回测结果
    '''
    def save_live_snapshot(self, strategy: StrategyBase, run_id: str, timestamp: datetime | None = None) -> None:
        snapshot_time = timestamp or datetime.utcnow()
        self.save_account_snapshot(
            account=strategy.account,
            run_id=run_id,
            trading_mode=strategy.trading_mode.value,
            timestamp=snapshot_time,
        )
        '''
        账户快照 -> account_snapshots
        持仓快照 -> position_snapshots
        订单状态 -> orders
        时间戳
        '''
        for position in strategy.positions.values():
            if not position.is_flat:
                self.save_position_snapshot(position, run_id=run_id, timestamp=snapshot_time, strategy_name=strategy.name)
        for order in strategy.orders.values():
            self.upsert_local_order(order, trading_mode=strategy.trading_mode.value, run_id=run_id, strategy_name=strategy.name)


    '''
    save_backtest_result()
    ↓
    create_run()
    ↓
    strategy_runs 新增一行，status=running
    ↓
    _save_result_orders()
    ↓
    orders 写入订单
    ↓
    _save_result_trades()
    ↓
    trades 写入成交
    ↓
    for result.equity_curve
    ↓
    save_equity_point()
    ↓
    equity_curve 写入权益点
    ↓
    finish_run()
    ↓
    strategy_runs 更新为 finished
    '''

    def save_backtest_result(
        self,
        result: Any,
        strategy_name: str,
        trading_mode: str,
        run_id: str | None = None,
        run_name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> StrategyRun:
        run = self.create_run(
            name=run_name or strategy_name,
            run_type="portfolio_backtest" if hasattr(result, "strategy_trades") else "backtest",
            trading_mode=trading_mode,
            strategy_name=strategy_name,
            initial_cash=result.equity_curve[0][1] if result.equity_curve else None,
            config=config,
            run_id=run_id,
        )
        actual_run_id = run.run_id
        self._save_result_orders(result, trading_mode, actual_run_id, strategy_name)
        self._save_result_trades(result, trading_mode, actual_run_id, strategy_name)
        for timestamp, equity in result.equity_curve:
            account = Account(
                cash=result.final_account.cash,
                equity=equity,
                available=result.final_account.available,
                margin=result.final_account.margin,
                maintenance_margin=result.final_account.maintenance_margin,
                margin_ratio=result.final_account.margin_ratio,
                realized_pnl=result.final_account.realized_pnl,
                unrealized_pnl=result.final_account.unrealized_pnl,
            )
            self.save_equity_point(
                timestamp=timestamp,
                account=account,
                strategy_name=strategy_name,
                run_id=actual_run_id,
                trading_mode=trading_mode,
            )
        return self.finish_run(actual_run_id, final_equity=result.final_account.equity)
    #高级封装方法是把多个底层保存方法串起来：save_live_snapshot 用于记录实盘/dry_run 当前状态，save_backtest_result 用于保存完整回测结果；前者偏运行中快照，后者偏回测结束后的完整归档。

#================================私有辅助方法=======================================

    '''
    _save_result_orders：从回测结果里提取订单并保存
    _save_result_trades：从回测结果里提取成交并保存
    _local_order_raw：把 LocalOrder 转成 JSON 字符串
    _trade_to_dict：把 Trade 转成 dict
    '''

    def _save_result_orders(self, result: Any, trading_mode: str, run_id: str, default_strategy_name: str) -> None:
            # 从回测结果中提取订单并保存到 orders 表。
            # 如果是组合回测，优先读取 result.strategy_orders，按策略名分别保存。
            # 如果是普通回测，则读取 result.orders，使用 default_strategy_name 保存。
        if hasattr(result, "strategy_orders") and result.strategy_orders:
            for strategy_name, orders in result.strategy_orders.items():
                for order in orders:
                    self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name)
            return
        for order in getattr(result, "orders", []):
            self.save_local_order(order, trading_mode=trading_mode, run_id=run_id, strategy_name=default_strategy_name)

    def _save_result_trades(self, result: Any, trading_mode: str, run_id: str, default_strategy_name: str) -> None:
            # 从回测结果中提取成交并保存到 trades 表。
            # 如果是组合回测，优先读取 result.strategy_trades，按策略名分别保存。
            # 如果是普通回测，则读取 result.trades，使用 default_strategy_name 保存。
        if hasattr(result, "strategy_trades") and result.strategy_trades:
            for strategy_name, trades in result.strategy_trades.items():
                for trade in trades:
                    self.save_framework_trade(trade, trading_mode=trading_mode, run_id=run_id, strategy_name=strategy_name)
            return
        for trade in getattr(result, "trades", []):
            self.save_framework_trade(trade, trading_mode=trading_mode, run_id=run_id, strategy_name=default_strategy_name)

    def _local_order_raw(self, order: LocalOrder) -> str:
            # 将框架内部 LocalOrder 转成 JSON 字符串，用于保存到 orders.raw。
            # raw 保存更完整的订单原始信息，便于排错和后续扩展。
        request = order.request
        return json.dumps(
            {
                "id": order.id,
                "symbol": request.symbol,
                "side": request.side.value,
                "type": request.order_type.value,
                "amount": request.amount,
                "price": request.price,
                "position_side": request.position_side.value if request.position_side is not None else None,
                "reduce_only": request.reduce_only,
                "time_in_force": request.time_in_force.value if request.time_in_force is not None else None,
                "params": request.params,
                "status": order.status.value,
                "filled": order.filled,
                "average": order.average,
                "created_at": order.created_at,
            },
            ensure_ascii=False,
            default=str,
        )

    def _trade_to_dict(self, trade: Trade) -> dict[str, Any]: # 将框架内部 Trade 转成 dict，供 save_framework_trade 序列化到 trades.raw。
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side.value,
            "amount": trade.amount,
            "price": trade.price,
            "fee": trade.fee,
            "traded_at": trade.traded_at,
        }
'''
models.py
= 定义数据库表模板
= Python ORM 类和 MySQL 表之间的映射关系

session.py
= 创建数据库连接和会话
= 管理 commit / rollback / close 的事务外壳

repository.py
= 真正执行具体业务读写
= 把框架对象写进表、从表里读回框架对象
'''