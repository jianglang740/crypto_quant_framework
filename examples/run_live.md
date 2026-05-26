# run_live.py 说明文档

## 作用

`run_live.py` 演示如何把 `LiveEngine`、`BinanceClient`、`MarketDataFetcher` 和策略串起来。

当前配置是：

```text
sandbox=True
dry_run=True
```

也就是说，它使用测试网配置和 dry_run 模式，不会真正发送实盘订单。

## 验证链路

```text
BinanceClient
↓
MarketDataFetcher.fetch_ohlcv()
↓
latest_bars()
↓
DataFeed
↓
SimpleMovingAverageStrategy
↓
LiveEngine.run()
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_live.py
```

## 前置条件

需要网络能访问 Binance Testnet 行情接口。

当前脚本没有配置 API Key，也没有配置代理。如果本地需要代理，需要手动修改 `BinanceConfig`。

## 是否真实下单

不会。

原因是：

```python
LiveConfig(dry_run=True)
```

在 dry_run 模式下，`LiveEngine` 会在本地模拟订单撮合。

## 是否写数据库

不会写数据库。

如果要记录数据库，需要结合 `LiveDatabaseRecorder` 或参考测试网记录脚本。

## 适合用来验证什么

```text
1. LiveEngine 的基本运行方式
2. data_provider 函数如何给 LiveEngine 提供最新 DataFeed
3. dry_run 模式下策略如何循环运行
4. MarketDataFetcher 如何拉取最新 K 线
```

## 注意事项

这个脚本会持续运行，需要手动中断。

如果网络不通或 Binance 访问失败，脚本会报连接相关错误。

它是 live 引擎结构演示，不是完整实盘部署脚本。
