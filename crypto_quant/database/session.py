'''
models.py 定义“表长什么样”
session.py 负责“怎么连接数据库、怎么提交/回滚/关闭一次数据库操作”

create_mysql_engine()
create_session_factory()
create_all_tables()
session_scope()
'''

'''
MySQLConfig
↓
create_mysql_engine()
↓
engine
↓
create_session_factory()
↓
Session 工厂
↓
session_scope(Session)
↓
一次具体数据库操作
'''

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from crypto_quant.config import MySQLConfig
from crypto_quant.database.models import Base


'''
Callable：表示“可以被调用的东西”，比如函数
Iterator：表示迭代器，这里用于 contextmanager 的类型标注
contextmanager：把一个函数变成 with 语句可用的上下文管理器
Engine：SQLAlchemy 的数据库连接引擎类型
create_engine：创建数据库连接引擎
Session：一次数据库会话
sessionmaker：创建 Session 的工厂
MySQLConfig：框架里的 MySQL 配置
Base：models.py 里所有 ORM 表的共同父类
'''

#这些函数可以说是数据库模块的“连接和事务工具箱”。它不关心业务，不关心订单、不关心 K 线，只负责：
'''
怎么连 MySQL
怎么创建 Session
怎么自动建表
怎么安全提交/回滚/关闭
'''

def create_mysql_engine(config: MySQLConfig) -> Engine: #用MySQLConfig创建一个SQLAlchemy的Engine,Engine是数据库连接引擎，不负责一次具体查询，而是负责“连接数据库的能力”
    return create_engine(config.url, echo=config.echo, pool_pre_ping=True, future=True)
#比如传入：
'''
config = MySQLConfig(
    host="127.0.0.1",
    port=3306,
    username="crypto_quant_user",
    password="...",
    database="crypto_quant",
)
config.url会生成类似mysql+pymysql://crypto_quant_user:密码@127.0.0.1:3306/crypto_quant?charset=utf8mb4的东西
然后create_engine(config.url, ...)，就会告诉SQLAlchemy：我要用 PyMySQL 驱动，连接这个 MySQL 数据库

echo=config.echo：控制是否打印 SQL 日志
pool_pre_ping=True：每次从连接池拿连接前，先 ping 一下数据库连接是否还活着
future=True：让 SQLAlchemy 使用较新的 API 风格，不重要
'''

def create_session_factory(engine: Engine) -> Callable[[], Session]: #用Engine创建一个Session工厂
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True) #以后这个工厂创建出来的 Session，都使用这个 engine 连接数据库，不要在某些查询前自动 flush，不要每执行一句就自动提交


def create_all_tables(engine: Engine) -> None: #根据models.py中所有继承Base的ORM类，自动在数据库里创建表
    Base.metadata.create_all(engine) #把models.py里定义的表结构，同步到MySQL，但不会重复建表，存在就跳过，不存在才建表

'''
with:
进入时做准备
中间执行代码
退出时自动收尾
'''
@contextmanager #把普通函数变成了一个可以配合with使用的上下文管理器，
def session_scope(session_factory: Callable[[], Session]) -> Iterator[Session]:
    session = session_factory() #创建Session工厂，打开一次数据库会话
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
'''
session = session_factory()
↓
yield session
↓
进入 with 代码块
↓
repo.create_run(...)
↓
with 代码块执行完
↓
回到 yield 后面
↓
session.commit()

如果 with 代码块没有报错，就执行:
session.commit() #提交事务，把这次数据库修改正式保存
如果with代码块中任何地方报错，就会进入except
session.rollback() #回滚事务，撤销这次未提交的数据库修改,然后raise：把原来的错误继续抛出去
session.close()：关闭这次数据库会话，释放连接资源

'''

#session.py 负责数据库连接和事务管理：create_mysql_engine 创建连接引擎，create_session_factory 创建 Session 工厂，create_all_tables 根据 models.py 自动建表，session_scope 用 with 自动 commit/rollback/close