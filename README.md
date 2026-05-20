# Crypto Quant Framework

一个基于 `ccxt`、面向 Binance 的初始加密货币量化框架，包含现货与 USD-M 合约模式、数据获取、MySQL 存储、策略基类、回测引擎、实盘引擎和绩效分析模块。

## 目录

```text
crypto_quant/
  analysis/      绩效分析
  data/          数据获取与 DataLine/DataFeed
  database/      MySQL ORM 与 Repository
  engine/        回测与实盘引擎
  exchange/      Binance ccxt 客户端封装
  strategy/      策略基类
examples/        示例策略与入口
```

## 安装

```bash
pip install -r requirements.txt
```

## 回测示例

```bash
python examples/run_backtest.py
```

## 设计要点

- `TradingMode.SPOT = "spot"`，`TradingMode.FUTURE = "future"`，与 Binance/ccxt 的 `defaultType` 对齐。
- 合约模式默认使用 Binance USD-M futures，即 `defaultType="future"`。
- 策略继承 `StrategyBase`，重写 `on_init`、`on_start`、`on_bar`、`on_trade`、`on_order`、`on_stop`。
- 回测数据使用 `DataFeed` 暴露 `open/high/low/close/volume/datetime` 数据线，可通过 `data.close[0]`、`data.close[-1]` 访问当前与历史值。
- 实盘引擎默认建议使用 `dry_run=True` 验证策略逻辑后再切换真实下单。

## MySQL 初始化

```python
from crypto_quant.config import MySQLConfig
from crypto_quant.database import Base, create_mysql_engine

engine = create_mysql_engine(MySQLConfig(password="your_password"))
Base.metadata.create_all(engine)
```

## 注意

此框架是初始骨架，不包含投资建议。真实交易前请充分回测、模拟盘验证并自行控制风险。
