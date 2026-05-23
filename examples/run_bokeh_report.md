# run_bokeh_report.py 说明文档

## 作用

`run_bokeh_report.py` 演示如何把回测结果生成 Bokeh HTML 报告。

它使用 `basic_strategy.py` 中的内置假行情和动量均线策略，运行回测后生成：

```text
backtest_report.html
```

## 验证链路

```text
build_demo_data()
↓
MomentumMovingAverageFuturesStrategy
↓
BacktestEngine.run()
↓
BokehBacktestReport
↓
backtest_report.html
```

## 运行方式

```bash
cd crypto_quant_framework-main
PYTHONPATH=. python examples/run_bokeh_report.py
```

## 前置条件

需要项目环境中已安装 Bokeh 相关依赖。

不需要 Binance。

不需要 MySQL。

不需要 API Key。

## 输出内容

终端输出：

```text
saved: backtest_report.html
```

项目目录下会生成：

```text
backtest_report.html
```

## 是否访问外部资源

不会访问外部网络。

## 是否写数据库

不会写数据库。

## 适合用来验证什么

```text
1. 回测报告模块是否可用
2. Bokeh HTML 文件是否能生成
3. 回测结果是否能可视化
```

## 注意事项

这是本地 HTML 报告示例，不是 Streamlit dashboard。后续如果做仪表盘，可以把这里的报告思路迁移到 dashboard 中。
