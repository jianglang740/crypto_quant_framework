from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from crypto_quant.config import MySQLConfig


def create_mysql_engine(config: MySQLConfig) -> Engine:
    return create_engine(config.url, echo=config.echo, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
