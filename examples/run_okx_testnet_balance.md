# run_okx_demo_balance.py 说明文档

## 作用

`run_okx_demo_balance.py` 用于验证 OKX Spot Testnet API Key / Secret 是否可用，并读取测试网账户余额。

这是测试网实盘记录验证的第一步。

## 验证链路

```text
环境变量中的测试网 API Key / Secret
↓
OKXConfig(sandbox=True)
↓
OKXClient
↓
load_markets()
↓
fetch_balance()
↓
打印非零资产余额
```

## 运行方式

```bash
cd crypto_quant_framework-main
export OKX_DEMO_API_KEY="你的测试网 Key"
export OKX_DEMO_SECRET_KEY="你的测试网 Secret"
PYTHONPATH=. python examples/run_okx_demo_balance.py
```

## 前置条件

需要：

```text
1. 已创建 OKX Spot Testnet API Key / Secret
2. 已设置环境变量 OKX_DEMO_API_KEY
3. 已设置环境变量 OKX_DEMO_SECRET_KEY
4. 本地 SOCKS5 代理 127.0.0.1:1080 可用
```

## 输出内容

脚本会打印：

```text
OKX Spot Testnet 连通性验证完成
市场数量
非零资产列表
每个资产的 free / used / total
```

## 是否写数据库

不会写数据库。

## 是否下单

不会下单。

## 适合用来验证什么

```text
1. API Key / Secret 是否正确
2. sandbox=True 是否生效
3. 测试网网络连接是否正常
4. 测试网账户余额是否能读取
```

## 安全注意事项

不要把 API Key / Secret 写进代码。

不要提交 `.env`、密钥、密码到 GitHub。

即使是测试网 Key，泄露后也建议删除并重新创建。
