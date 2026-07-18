from datetime import datetime
from decimal import Decimal

'''
DateTime:定义数据库中的日期时间类型字段
Index:用于创建数据库索引，优化查询性能
Numeric:高精度数值类型，常用于存储金额、精确小数
String:可变长度字符串类型
Text:大文本类型，适合存储长文本内容
Boolean:布尔类型(True/False)
DeclarativeBase:声明式基类，所有 ORM 模型都需要继承它
Mapped:类型注解标记，用于声明模型字段的类型
mapped_column:定义 ORM 模型中的数据库列，替代旧版的 Column
'''

from sqlalchemy import DateTime, Index, Numeric, String, Text, Boolean
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass
'''
Base 是所有 ORM 表类的共同父类
后面所有表都继承 Base
SQLAlchemy 会通过 Base 收集所有表定义
'''

class StrategyRun(Base): #定义策略运行数据表类，StrategyRun 是 Python 里的 ORM 类
    __tablename__ = "strategy_runs" #将数据表命名为strategy_runs，strategy_runs 是 MySQL 里的真实表名，即策略运行数据表

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #主键，自增ID
    run_id: Mapped[str] = mapped_column(String(64), unique=True) #策略一次运行的唯一ID，比如同一个策略跑三次不同的参数，它的作用非常重要：把其他表的数据关联回这一次运行
    name: Mapped[str] = mapped_column(String(128)) #这是这次运行的名字，比如mysql_datafeed_backtest_save_test，是给人看的，方便你在数据库或仪表盘里识别
    run_type: Mapped[str] = mapped_column(String(32)) #表示这次运行是什么类型，比如backtest、portfolio_backtest、dry_run、live、manual_test，即这条 strategy_runs 记录代表什么运行场景
    trading_mode: Mapped[str] = mapped_column(String(16)) #交易类型，现货还是合约
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True) #这个策略的名字，比如simple_moving_average，可以为null
    symbols: Mapped[str | None] = mapped_column(Text, nullable=True) #表示这次运行涉及哪些交易对，可以有多个交易对，也可以是空值
    timeframe: Mapped[str | None] = mapped_column(String(16), nullable=True) #表示k线的周期，可以是空值
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #表示这次运行开始时间，如果没有上传时间，就默认是当前时间
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True) #表示这次运行结束时间，刚创建 run 的时候，它通常还没结束，所以可以为空
    initial_cash: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #表示初始资金，高精度
    final_equity: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #表示最终权益，刚创建 run 时还不知道最终权益，所以允许为空，结束后调用finish_run(...)才会显示它
    status: Mapped[str] = mapped_column(String(32), default="created") #表示这次运行的状态
    config: Mapped[str | None] = mapped_column(Text, nullable=True) #表示这次运行的配置
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #表示这条数据库记录创建时间
    '''
    started_at 可能是历史回测开始时间
    created_at 是今天导入数据库的时间
    strategy_runs 不是记录交易明细的表，而是记录“每一次策略运行总档案”的主表；其他订单、成交、权益曲线等明细表通过 run_id 归属于它。
    '''


class Kline(Base): #定义k线数据表类，Kline是Python 里的 ORM 类
    __tablename__ = "klines" #将数据表命名为klines

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #某根k线的ID，自增主键
    exchange: Mapped[str] = mapped_column(String(32), default="okx") #交易所，这条k线数据是从哪里来的？默认是 OKX
    symbol: Mapped[str] = mapped_column(String(32)) #k线对应的交易对的名称
    timeframe: Mapped[str] = mapped_column(String(16)) #k线周期
    open_time: Mapped[datetime] = mapped_column(DateTime) #开盘时间，一根 K 线的时间，本质上通常指这根 K 线的开盘时间
    open: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #开盘价
    high: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #最高价
    low: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #最低价
    close: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #收盘价
    volume: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #成交量

    __table_args__ = (Index("uq_klines_exchange_symbol_tf_time", "exchange", "symbol", "timeframe", "open_time", unique=True),)
    '''
    __table_args__ = (...)这是 SQLAlchemy 的特殊写法，用来给这张表添加额外规则
    exchange + symbol + timeframe + open_time 这四个字段加起来必须唯一,才能万无一失的确定一根k线
    klines 表用来保存行情 K 线；open_time 是这根 K 线的开始时间；exchange + symbol + timeframe + open_time 组成唯一索引，用来防止重复 K 线，并支持 upsert 更新。
    '''

    '''
    orders 表：记录你发过哪些订单，以及订单状态
    trades 表：记录实际成交了哪些交易
    '''
class OrderRecord(Base): #定义订单记录数据表类，OrderRecord是Python 里的 ORM 类
    __tablename__ = "orders" #将交易记录数据表命名为orders,保存回测 / dry_run / live 中产生的订单记录

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #这条记录的ID，主键自增,每一行订单记录都有一个数据库内部 ID
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True) #运行ID，可以为空,表示这笔订单属于哪一次运行,通常对应strategy_runs.run_id
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True) #表示这笔订单由哪个策略产生，可以为空
    exchange: Mapped[str] = mapped_column(String(32), default="okx") #表示这笔订单在哪个交易所，默认 OKX
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True) #这是交易所返回的订单ID，比如通过 OKX API 下单，OKX 会返回一个自己的订单号
    client_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True) #这是客户端订单 ID，也就是我们自己的程序生成的订单号
    symbol: Mapped[str] = mapped_column(String(32)) #订单交易对
    trading_mode: Mapped[str] = mapped_column(String(16)) #交易模式，是现货还是合约？
    side: Mapped[str] = mapped_column(String(16)) #订单方向，买还是卖？
    order_type: Mapped[str] = mapped_column(String(32)) #订单类型，详见枚举模块
    status: Mapped[str] = mapped_column(String(32)) #订单状态，对应OrderStatus枚举
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #订单数量，比如买入 0.01 BTC，高精度
    price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #订单价格，对于限价单可能price = 50000，对于市价单可能为NULL
    filled: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #已经成交的数量，默认数量是0，因为刚创建订单时可能还没有成交
    average: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #平均成交价
    position_side: Mapped[str | None] = mapped_column(String(16), nullable=True) #持仓方向
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False) #是否只减仓，主要用于合约交易
    time_in_force: Mapped[str | None] = mapped_column(String(16), nullable=True) #订单有效方式
    raw: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True) #原始数据，通常用来保存交易所 API返回的原始JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #这条订单记录创建时间，注意它不是一定等于订单成交时间
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True) #这条订单记录最后更新时间，每次订单状态变化，都可以更新updated_at，可空是因为刚创建时可能还没有更新过

    __table_args__ = (Index("ix_orders_run_strategy", "run_id", "strategy_name"),) #定义了一个普通索引，某一次回测产生了哪些订单？某一个策略在这次运行里产生了哪些订单？

    '''
    orders 是委托
    trades 是成交
    
    '''
class TradeRecord(Base): #定义成交纪录数据表类，TradeRecord是Python 里的 ORM 类
    __tablename__ = "trades" #将成交纪录数据表命名为trades

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #ID，自增主键
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True) #运行ID，可以为空,表示这笔订单属于哪一次运行,通常对应strategy_runs.run_id
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True) #策略名称，可以为空
    exchange: Mapped[str] = mapped_column(String(32), default="okx") #这笔成交纪录的交易所，默认是 OKX
    exchange_trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True) #交易所返回的成交ID
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True) #这笔成交对应的交易所订单ID
    trading_mode: Mapped[str | None] = mapped_column(String(16), nullable=True) #交易模式，是现货还是合约？
    symbol: Mapped[str] = mapped_column(String(32)) #交易对名称
    side: Mapped[str] = mapped_column(String(16)) #交易方向，买还是卖？
    position_side: Mapped[str | None] = mapped_column(String(16), nullable=True) #持仓方向，对应enmus里的枚举，是多头还是空头还是both
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #成交数量
    price: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #成交价格
    fee: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #手续费
    fee_asset: Mapped[str | None] = mapped_column(String(32), nullable=True) #手续费币种
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #已实现盈亏
    traded_at: Mapped[datetime] = mapped_column(DateTime) #成交时间
    raw: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True) #原始数据，通常用来保存交易所 API返回的原始JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #创建时间

    __table_args__ = (Index("ix_trades_run_strategy", "run_id", "strategy_name"),)


class EquityCurve(Base): #定义权益曲线表类，EquityCurve是Python 里的 ORM 类
    __tablename__ = "equity_curve" #将权益曲线记录表命名为equity_curve

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #ID，自增主键
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True) #运行ID，可以为空,表示这笔订单属于哪一次运行,通常对应strategy_runs.run_id
    strategy_name: Mapped[str] = mapped_column(String(128)) #策略名称
    trading_mode: Mapped[str | None] = mapped_column(String(16), nullable=True) #交易模式，是合约还是现货？
    timestamp: Mapped[datetime] = mapped_column(DateTime) #时间戳
    cash: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #现金余额
    equity: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #账户权益
    available: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #可用余额
    margin: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #保证金
    maintenance_margin: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #维持保证金金额
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #已实现盈亏
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #未实现盈亏

    __table_args__ = (Index("ix_equity_curve_run_time", "run_id", "timestamp"),) #设置普通索引，为run_id和timestamp


class AccountSnapshot(Base): #定义账户快照数据表类，AccountSnapshot是Python 里的 ORM 类
    __tablename__ = "account_snapshots" #将账户快照数据表命名为account_snapshots

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #ID，主键自增
    run_id: Mapped[str] = mapped_column(String(64)) #运行ID，必须有，用来归属某一次 dry_run/live 运行
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #时间戳
    trading_mode: Mapped[str] = mapped_column(String(16)) #交易模式，是合约还是现货
    cash: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #现金余额
    equity: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #账户权益
    available: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #可用余额
    margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #保证金
    maintenance_margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #维持保证金金额
    margin_ratio: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #保证金率，合约回测中用于衡量账户风险
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #已实现盈亏
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #未实现盈亏
    raw: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True) #原始数据，通常用来保存交易所 API返回的原始JSON

    __table_args__ = (Index("ix_account_snapshots_run_time", "run_id", "timestamp"),) #设置普通索引，run_id和timestamp
 

class PositionSnapshot(Base): #定义持仓快照数据表类，PositionSnapshot是Python 里的 ORM 类
    __tablename__ = "position_snapshots" #将持仓快照数据表命名为position_snapshots

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True) #ID，主键自增
    run_id: Mapped[str] = mapped_column(String(64)) #运行ID，必须有，用来归属某一次 dry_run/live 运行
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True) #策略名称，可以为空值
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow) #时间戳
    symbol: Mapped[str] = mapped_column(String(32)) #交易对名称
    side: Mapped[str] = mapped_column(String(16)) #持仓方向，这笔持仓是多头、空头，还是普通/单向持仓
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18)) #持仓数量
    entry_price: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #持仓开仓均价
    mark_price: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #标记价格/当前估值价格，常用于计算浮盈浮亏
    margin: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #保证金
    liquidation_price: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True) #强平价格，主要用于合约，可为空
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(36, 18), default=Decimal("0")) #未实现盈亏
    raw: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True) #原始数据，通常用来保存交易所 API返回的原始JSON

    __table_args__ = (Index("ix_position_snapshots_run_time", "run_id", "timestamp"),) #设置普通索引，为run_id和timestamp