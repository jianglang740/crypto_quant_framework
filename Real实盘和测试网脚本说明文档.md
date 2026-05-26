# `real/` 实盘和测试网脚本说明文档

本文档说明项目根目录下 `real/` 文件夹的定位、环境变量配置、MySQL 建表流程、Binance Spot Testnet 长跑脚本，以及将数据同步到 Streamlit 仪表盘时的推荐部署顺序。

`real/` 不是回测示例目录，也不是仪表盘目录。它用于放置更接近真实运行环境的脚本，例如：

```text
实盘 / 模拟盘 / 测试网长跑脚本
        ↓
持续写入 MySQL
        ↓
Streamlit dashboard 只读展示
```

---

## 1. 当前文件

```text
real/
├── init_mysql_tables.py             # 只初始化 MySQL 表结构，不连接交易所，不下单
└── run_testnet_smoke_strategy.py    # Binance Spot Testnet 小额循环开平仓 + 持续写数据库
```

项目根目录还有：

```text
.env.example                         # 环境变量模板，不包含真实密钥
```

---

## 2. `real/` 的设计边界

`real/` 脚本负责：

```text
1. 连接 MySQL；
2. 创建或读取 strategy_runs；
3. 写入 account_snapshots；
4. 写入 position_snapshots；
5. 写入 orders；
6. 写入 trades；
7. 写入 equity_curve；
8. 驱动测试网 / 模拟盘策略持续运行。
```

仪表盘负责：

```text
1. 读取 MySQL；
2. 展示运行记录；
3. 展示账户、持仓、订单、成交和回测结果；
4. 展示快照延迟和运行状态。
```

仪表盘不负责：

```text
1. 下单；
2. 撤单；
3. 修改策略参数；
4. 启动或停止策略；
5. 修改交易状态。
```

---

## 3. 环境变量文件

建议复制模板：

```bash
cp .env.example .env
```

然后编辑：

```bash
nano .env
```

`.env.example` 使用统一的 `CRYPTO_QUANT_*` 命名：

```bash
export CRYPTO_QUANT_MYSQL_HOST="127.0.0.1"
export CRYPTO_QUANT_MYSQL_PORT="3306"
export CRYPTO_QUANT_MYSQL_USERNAME="crypto_quant_user"
export CRYPTO_QUANT_MYSQL_PASSWORD="change_me"
export CRYPTO_QUANT_MYSQL_DATABASE="crypto_quant"

export CRYPTO_QUANT_BINANCE_TESTNET_API_KEY="change_me"
export CRYPTO_QUANT_BINANCE_TESTNET_SECRET_KEY="change_me"

export CRYPTO_QUANT_BINANCE_PROXY_URL=""

export CRYPTO_QUANT_TESTNET_SYMBOL="BTC/USDT"
export CRYPTO_QUANT_TESTNET_BASE_ASSET="BTC"
export CRYPTO_QUANT_TESTNET_QUOTE_ASSET="USDT"
export CRYPTO_QUANT_TESTNET_TRADE_NOTIONAL_USDT="20"
export CRYPTO_QUANT_TESTNET_SNAPSHOT_INTERVAL_SECONDS="30"
export CRYPTO_QUANT_TESTNET_HOLD_SNAPSHOTS="2"
export CRYPTO_QUANT_TESTNET_MAX_CYCLES="3"
export CRYPTO_QUANT_TESTNET_RUN_ID=""
```

运行脚本前加载：

```bash
source .env
```

注意：

```text
.env.example 可以提交；
.env 不要提交；
.env 里不要放正式实盘 API key，测试网阶段只放 Binance Spot Testnet key。
```

如果部署在云服务器上，建议限制权限：

```bash
chmod 600 .env
```

---

## 4. MySQL 建表脚本

文件：

```text
real/init_mysql_tables.py
```

用途：

```text
只连接 MySQL 并创建项目所需表结构。
不连接 Binance。
不下单。
不插入测试交易数据。
```

运行：

```bash
source .env
python real/init_mysql_tables.py
```

成功后会输出类似：

```text
MySQL tables are ready: 127.0.0.1:3306/crypto_quant
```

它会创建这些表：

```text
strategy_runs
klines
orders
trades
equity_curve
account_snapshots
position_snapshots
```

该脚本内部调用：

```python
create_all_tables(engine)
```

因此可以重复运行：

```text
表不存在：创建；
表已存在：跳过；
不会清空数据；
不会删除表；
不会重复创建同名表。
```

---

## 5. Binance Spot Testnet 长跑脚本

文件：

```text
real/run_testnet_smoke_strategy.py
```

定位：

```text
测试网冒烟策略 / 长时间链路验证脚本。
```

它不是盈利策略，目标是测试完整链路：

```text
Binance Spot Testnet
        ↓
小额市价买入 / 持有 / 市价卖出
        ↓
orders / trades
        ↓
account_snapshots / position_snapshots / equity_curve
        ↓
dashboard 实盘速览
```

运行：

```bash
source .env
python real/run_testnet_smoke_strategy.py
```

第一次建议先短跑：

```bash
export CRYPTO_QUANT_TESTNET_MAX_CYCLES="3"
python real/run_testnet_smoke_strategy.py
```

确认数据库写入正常后，再改为长期运行：

```bash
export CRYPTO_QUANT_TESTNET_MAX_CYCLES="0"
python real/run_testnet_smoke_strategy.py
```

`CRYPTO_QUANT_TESTNET_MAX_CYCLES="0"` 表示无限循环。

---

## 6. testnet 脚本写入哪些表

启动时创建：

```text
strategy_runs
```

运行过程中持续写入：

```text
account_snapshots
position_snapshots
equity_curve
orders
trades
```

停止方式：

```text
Ctrl+C：strategy_runs.status 更新为 stopped；
异常退出：strategy_runs.status 更新为 failed；
达到最大循环次数：strategy_runs.status 更新为 finished。
```

`run_type` 会写为：

```text
testnet
```

因此仪表盘的“实盘速览”页面可以读取到这类运行记录。

---

## 7. 推荐云服务器部署顺序

假设项目目录为：

```bash
~/code/crypto_quant_framework-main
```

推荐顺序：

```bash
conda activate quant
cd ~/code/crypto_quant_framework-main
pip install -e .
cp .env.example .env
nano .env
source .env
python real/init_mysql_tables.py
```

然后检查数据库：

```sql
use crypto_quant;
show tables;
select run_id, run_type, status, strategy_name, created_at
from strategy_runs
order by id desc
limit 5;
```

短跑 testnet：

```bash
export CRYPTO_QUANT_TESTNET_MAX_CYCLES="3"
python real/run_testnet_smoke_strategy.py
```

再检查：

```sql
select count(*) from strategy_runs;
select count(*) from account_snapshots;
select count(*) from position_snapshots;
select count(*) from orders;
select count(*) from trades;
```

确认数据正常后启动仪表盘：

```bash
streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

本地电脑通过 SSH 隧道访问：

```bash
ssh -L 8501:127.0.0.1:8501 ubuntu@你的服务器公网IP
```

然后浏览器打开：

```text
http://localhost:8501
```

---

## 8. 安全注意事项

1. 不要把 `.env` 提交到 GitHub。
2. 不要把正式实盘 API key 放入测试脚本。
3. 第一轮测试只使用 Binance Spot Testnet key。
4. MySQL 不建议开放公网端口。
5. Streamlit dashboard 不建议直接裸露公网。
6. 如果必须公网访问 dashboard，应使用 Nginx、Basic Auth、安全组白名单或 VPN。
7. 长期运行前应补充日志、进程守护、异常告警和手动兜底流程。

---

## 9. 关于 K 线图

`run_testnet_smoke_strategy.py` 主要写交易、快照和权益数据，不负责持续同步 K 线。

因此 dashboard 的“实盘速览”可以正常显示：

```text
运行记录
账户快照
持仓快照
订单
成交
快照延迟
快照状态
```

但如果 `klines` 表里没有对应交易对和周期的 K 线，行情图可能提示暂无数据。

这不影响 testnet 长跑链路验证。后续如果需要行情图，也可以单独做 K 线同步脚本或导入 CSV。
