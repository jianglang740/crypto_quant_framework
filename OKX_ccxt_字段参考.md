# OKX + ccxt 字段参考

## 1. ccxt 连接配置

```python
exchange = ccxt.okx({
    "apiKey": "...",          # OKX API Key
    "secret": "...",          # OKX Secret Key
    "password": "...",        # OKX Passphrase（必须）
    "enableRateLimit": True,  # 自动限频
    "proxies": {              # 代理（可选）
        "http": "socks5h://127.0.0.1:1080",
        "https": "socks5h://127.0.0.1:1080",
    },
})
exchange.set_sandbox_mode(True)  # demo 环境
```

---

## 2. defaultType — 切换交易市场

```python
ex.options["defaultType"] = "spot"   # 现货
ex.options["defaultType"] = "swap"   # 永续合约
```

---

## 3. 交易对格式

| 市场       | ccxt 格式    | OKX 原生格式      |
| ---------- | ------------ | ----------------- |
| 现货       | `ETH/USDT` | `ETH-USDT`      |
| 永续合约   | `ETH/USDT` | `ETH-USDT-SWAP` |
| 代币化股票 | `XMU/USDT` | `XMU-USDT`      |

---

## 4. 现货下单

```python
ex.options["defaultType"] = "spot"

order = ex.create_order(
    symbol="ETH/USDT",       # 交易对
    type="market",           # market / limit
    side="buy",              # buy / sell
    amount=0.01,             # 币的数量（比如 0.01 ETH）
    price=1800,              # 限价单才需要，市价单省略
)

fetched = ex.fetch_order(order["id"], "ETH/USDT")  # 补查状态
```

---

## 5. 合约下单

```python
ex.options["defaultType"] = "swap"

# 必须先设杠杆和保证金模式
ex.set_margin_mode("cross", "ETH/USDT", {"lever": 10})
ex.set_leverage(10, "ETH/USDT")

order = ex.create_order(
    symbol="ETH/USDT",
    type="market",
    side="buy",
    amount=1,                             # 合约张数（不是币数量）
    params={"posSide": "long"},           # 双向持仓时必传，单向可不传
)
```

### posSide

| 值          | 含义 |
| ----------- | ---- |
| `"long"`  | 做多 |
| `"short"` | 做空 |

---

## 6. margin mode

```python
ex.set_margin_mode("cross", "ETH/USDT", {"lever": 10})    # 全仓
ex.set_margin_mode("isolated", "ETH/USDT", {"lever": 10})  # 逐仓
```

---

## 7. 账户与持仓

```python
# 查余额
spot_bal = ex.fetch_balance({"type": "spot"})
swap_bal = ex.fetch_balance({"type": "swap"})

spot_bal["free"]["USDT"]    # 可用
spot_bal["total"]["USDT"]   # 总额
spot_bal["used"]["USDT"]    # 占用（冻结）

# 查合约持仓
positions = ex.fetch_positions(["ETH/USDT"], {"type": "swap"})
p = positions[0]
p["contracts"]       # 持仓张数
p["entryPrice"]      # 开仓均价
p["markPrice"]       # 标记价格
p["unrealizedPnl"]   # 未实现盈亏
p["liquidationPrice"]# 强平价格
p["side"]            # long / short
```

---

## 8. OKX 原生字段（balance info 内）

查余额返回的 `balance["info"]` 里：

| OKX 字段    | 含义       |
| ----------- | ---------- |
| `totalEq` | 账户总权益 |
| `adjEq`   | 可用保证金 |
| `imr`     | 初始保证金 |
| `mmr`     | 维持保证金 |
| `upl`     | 未实现盈亏 |

## 9. OKX 原生字段（position info 内）

查持仓返回的 `raw_position["info"]` 里：

| OKX 字段    | 含义                      |
| ----------- | ------------------------- |
| `pos`     | 持仓张数                  |
| `avgPx`   | 开仓均价                  |
| `markPx`  | 标记价格                  |
| `liqPx`   | 强平价格                  |
| `upl`     | 未实现盈亏                |
| `imr`     | 保证金                    |
| `posSide` | 持仓方向 (long/short)     |
| `instId`  | 交易对 (如 ETH-USDT-SWAP) |
| `lever`   | 杠杆倍数                  |

## 10. ccxt 统一字段 vs OKX 原生字段 对照

| 含义       | ccxt 统一                    | OKX 原生 info       |
| ---------- | ---------------------------- | ------------------- |
| 账户权益   | `balance["total"]["USDT"]` | `info["totalEq"]` |
| 可用余额   | `balance["free"]["USDT"]`  | `info["adjEq"]`   |
| 保证金     | —                           | `info["imr"]`     |
| 维持保证金 | —                           | `info["mmr"]`     |
| 持仓张数   | `raw["contracts"]`         | `info["pos"]`     |
| 开仓均价   | `raw["entryPrice"]`        | `info["avgPx"]`   |
| 标记价格   | `raw["markPrice"]`         | `info["markPx"]`  |
| 强平价格   | `raw["liquidationPrice"]`  | `info["liqPx"]`   |
| 未实现盈亏 | `raw["unrealizedPnl"]`     | `info["upl"]`     |
| 持仓方向   | `raw["side"]`              | `info["posSide"]` |
| 交易对     | `raw["symbol"]`            | `info["instId"]`  |

---

## 11. tdMode（OKX 原生参数，raw API 用）

| 值             | 场景     |
| -------------- | -------- |
| `"cash"`     | 现货     |
| `"cross"`    | 合约全仓 |
| `"isolated"` | 合约逐仓 |

---

## 12. 订单类型和方向

### side

| 值         | 含义 |
| ---------- | ---- |
| `"buy"`  | 买入 |
| `"sell"` | 卖出 |

### type

| 值           | 含义   |
| ------------ | ------ |
| `"market"` | 市价单 |
| `"limit"`  | 限价单 |

---

## 13. 常见 OKX 错误码

| sCode     | sMsg                                      | 解决                               |
| --------- | ----------------------------------------- | ---------------------------------- |
| `51000` | Parameter side error                      | 检查`defaultType` 和 `posSide` |
| `51008` | Available balance insufficient            | 余额不足或没设杠杆                 |
| `51010` | Can't complete under current account mode | 网页端切换账户模式为单币种保证金   |
| `51001` | Instrument ID doesn't exist               | 交易对不存在或格式错误             |
| `50101` | APIKey doesn't match current environment  | 没调`set_sandbox_mode(True)`     |
| `50102` | Timestamp request expired                 | 时间戳不同步                       |
