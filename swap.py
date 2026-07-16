import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ========== 保留您的BinanceUsdtSwapAccount类（未修改） ==========
class BinanceUsdtSwapAccount:
    """
    币安USDT永续合约 账户实体类
    所有字段1:1对齐币安网页/API原生字面量
    """
    def __init__(self):
        # ========== 账户资金层字段 ==========
        self.wallet_balance = 0.0          # 钱包余额(不含浮动盈亏)
        self.unrealized_pnl = 0.0          # 未实现浮动盈亏
        self.margin_balance = 0.0          # 保证金余额 = 钱包余额+浮动盈亏（浮动盈亏可正可负）
        self.available_balance = 0.0      # 可用余额(可新开仓)
        self.transferable_balance = 0.0    # 可转出余额
        self.initial_margin = 0.0          # 持仓占用初始保证金
        self.maintenance_margin = 0.0      # 维持保证金(爆仓临界)
        self.margin_ratio = 0.0            # 保证金率
        self.trades = []
        
        # ========== 交易全局配置 ==========
        self.leverage = 50                  # 默认杠杆
        self.margin_mode = "isolated"      # isolated逐仓 / cross全仓
        self.position_mode = "one_way"     # one_way单向 / hedge双向
        
        # ========== 持仓状态枚举 ==========
        self.POS_EMPTY = 0 # 无持仓
        self.POS_LONG = 1 # 多头持仓
        self.POS_SHORT = -1 # 空头持仓
        self.pos_status = self.POS_EMPTY   # 当前持仓状态,默认无持仓
        
        # ========== 单个持仓信息 ==========
        self.symbol = ""
        self.position_size = 0.0             # 持仓数量
        self.entry_price = 0.0              # 开仓均价
        self.mark_price = 0.0               # 标记价格
        self.liq_price = 0.0                # 强平价格
        self.isolated_margin = 0.0          # 逐仓占用保证金
        
        # ========== 交易费率 ==========
        self.trade_fee_rate = 0.001        # 双边手续费

    def reset_account(self, init_usdt: float):
        """初始化合约账户资金"""
        self.wallet_balance = init_usdt # 钱包余额初始值为转入的USDT数量
        self.margin_balance = init_usdt # 保证金余额初始值为转入的USDT数量（因为初始无持仓，所以保证金余额=钱包余额）
        self.available_balance = init_usdt # 可用余额初始值为转入的USDT数量（因为初始无持仓，所以可用余额=钱包余额）
        self.unrealized_pnl = 0.0 # 初始无持仓，所以浮动盈亏为0
        self.initial_margin = 0.0 # 初始无持仓，所以占用保证金为0
        self.pos_status = self.POS_EMPTY # 初始无持仓
        self.position_size = 0.0 # 初始无持仓，所以持仓数量为0
    
    def _calc_occupy_margin(self, trade_value: float) -> float:
        """计算开仓占用保证金"""
        return trade_value / self.leverage # 占用保证金=交易价值/杠杆倍数

    # ====================== 做多全套方法 ======================
    def open_long(self, date,symbol: str, price: float, trade_amt: float):
        """
        开多仓
        :param symbol: 交易对
        :param price: 开仓价格
        :param trade_amt: 开仓数量
        """
        if self.pos_status != self.POS_EMPTY:
            return False, "已有持仓，禁止重复开仓"
        
        self.symbol = symbol
        trade_value = price * trade_amt # 计算交易价值=开仓价格*开仓数量
        occupy_margin = self._calc_occupy_margin(trade_value) # 计算占用保证金=交易价值/杠杆倍数
        fee = trade_value * self.trade_fee_rate # 计算手续费=交易价值*双边手续费率

        # 资金扣除
        if self.available_balance < occupy_margin + fee: #可用资金小于占用保证金+手续费，开仓失败
            return False, "可用资金不足"
        self.wallet_balance -= fee # 钱包余额扣除手续费
        self.available_balance -= (occupy_margin + fee) # 可用余额扣除占用保证金和手续费
        self.initial_margin += occupy_margin # 占用保证金增加

        # 更新持仓
        self.pos_status = self.POS_LONG
        self.position_size = trade_amt
        self.entry_price = price # 开仓均价=开仓价格
        self.trades.append({
            "type": "LONG", 
            "date": date, 
            "symbol": symbol, 
            "price": price, 
            "amount": trade_amt, 
            "margin": occupy_margin, 
            "fee": fee,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance
        })
        return True, f"开多成功，数量:{trade_amt:.4f},占用保证金:{occupy_margin:.2f},手续费:{fee:.2f}，开仓价格:{price:.2f}"

    def close_long(self, date,close_price: float) -> tuple[bool, str, float]:
        """平多仓，返回状态+信息+净盈亏"""
        if self.pos_status != self.POS_LONG: #如果持仓状态不是多头，说明没有多头持仓，无法平多，返回失败状态和提示信息，以及0盈亏
            return False, "无多头持仓", 0.0
        
        # 多头盈亏公式
        gross_pnl = (close_price - self.entry_price) * self.position_size #毛盈亏=（平仓价格-开仓价格）*持仓数量
        close_fee = close_price * self.position_size * self.trade_fee_rate #平仓手续费=平仓价格*持仓数量*双边手续费率
        net_pnl = gross_pnl - close_fee #净盈亏=毛盈亏-平仓手续费（开仓手续费已在开仓时扣除，这里不再考虑）

        # 归还保证金+结算盈亏
        self.wallet_balance += net_pnl # 钱包余额增加盈亏结果（盈亏为正则增加，盈亏为负则减少）
        self.available_balance += self.initial_margin + net_pnl # 可用余额增加归还的占用保证金
        self.initial_margin = 0.0 # 占用保证金清零

        # 清空持仓
        self.pos_status = self.POS_EMPTY #回归到无持仓状态
        self.position_size = 0.0 #持仓数量清零
        self.entry_price = 0.0 #开仓价格清零
        self.trades.append({
            "type": "CLOSE_LONG", 
            "date": date, 
            "symbol": self.symbol, 
            "price": close_price, 
            "amount": self.position_size, 
            "fee": close_fee,
            "pnl": net_pnl,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance
        })
        return True, f"平多完成，净盈亏:{net_pnl:.2f} USDT,手续费:{close_fee:.2f}，平仓价格:{close_price:.2f}", net_pnl

    # ====================== 做空全套方法 ======================
    def open_short(self, date, symbol: str, price: float, trade_amt: float):
        """开空仓"""
        if self.pos_status != self.POS_EMPTY:
            return False, "已有持仓，禁止重复开仓"
        
        self.symbol = symbol
        trade_value = price * trade_amt # 计算交易价值=开仓价格*开仓数量
        occupy_margin = self._calc_occupy_margin(trade_value) # 计算占用保证金=交易价值/杠杆倍数
        fee = trade_value * self.trade_fee_rate # 计算手续费=交易价值*双边手续费率

        if self.available_balance < occupy_margin + fee: #可用资金小于占用保证金+手续费，开仓失败
            return False, "可用资金不足"
        self.wallet_balance -= fee # 钱包余额扣除手续费
        self.available_balance -= (occupy_margin + fee) # 可用余额扣除占用保证金和手续费
        self.initial_margin += occupy_margin # 占用保证金增加

        self.pos_status = self.POS_SHORT # 更新持仓状态为做空
        self.position_size = trade_amt # 更新持仓数量为开空数量
        self.entry_price = price # 开仓均价=开仓价格
        self.trades.append({
            "type": "SHORT", 
            "date": date, 
            "symbol": symbol, 
            "price": price, 
            "amount": trade_amt, 
            "margin": occupy_margin, 
            "fee": fee,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance
        })
        return True, f"开空成功，数量:{trade_amt:.4f},占用保证金:{occupy_margin:.2f},手续费:{fee:.2f}，开仓价格:{price:.2f}"

    def close_short(self, date, close_price: float) -> tuple[bool, str, float]:
        """平空仓"""
        if self.pos_status != self.POS_SHORT:
            return False, "无空头持仓", 0.0
        
        # 空头盈亏公式
        gross_pnl = (self.entry_price - close_price) * self.position_size # 毛盈亏=（开仓价格-平仓价格）*持仓数量
        close_fee = close_price * self.position_size * self.trade_fee_rate # 平仓手续费=平仓价格*持仓数量*双边手续费率
        net_pnl = gross_pnl - close_fee # 净盈亏=毛盈亏-平仓手续费

        self.wallet_balance += net_pnl # 钱包余额增加盈亏结果
        self.available_balance += self.initial_margin + net_pnl # 可用余额增加归还的占用保证金
        self.initial_margin = 0.0 # 占用保证金清零

        self.pos_status = self.POS_EMPTY # 回归到无持仓状态
        self.position_size = 0.0 # 持仓数量清零
        self.entry_price = 0.0 # 开仓价格清零   
        self.trades.append({
            "type": "CLOSE_SHORT", 
            "date": date, 
            "symbol": self.symbol, 
            "price": close_price, 
            "amount": self.position_size, 
            "fee": close_fee,
            "pnl": net_pnl,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance
        })
        return True, f"平空完成，净盈亏:{net_pnl:.2f} USDT,手续费:{close_fee:.2f}，平仓价格:{close_price:.2f}", net_pnl

    # ====================== 通用工具方法 ======================
    def get_unrealized_pnl(self, date, now_price: float) -> float:
        """获取当前持仓浮动盈亏"""
        if self.pos_status == self.POS_LONG:
            return (now_price - self.entry_price) * self.position_size
        elif self.pos_status == self.POS_SHORT:
            return (self.entry_price - now_price) * self.position_size
        return 0.0

    def close_all_position(self, date, now_price: float):
        """一键全平所有持仓"""
        if self.pos_status == self.POS_LONG:
            return self.close_long(date, now_price)
        elif self.pos_status == self.POS_SHORT:
            return self.close_short(date, now_price)
        return True, "暂无持仓", 0.0

# ========== 数据加载工具类 ==========
class DataLoader:
    """数据加载类（解耦数据逻辑）"""
    @staticmethod
    def get_data_from_csv(file_path="ETH_USDT_5m_1year.csv"):
        df = pd.read_csv(file_path)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df.set_index("datetime", inplace=True)
        # 确保有close列
        if "close" not in df.columns:
            raise ValueError("CSV文件必须包含'close'列（收盘价）")
        return df

# ========== 指标计算类 ==========
class IndicatorCalculator:
    """指标计算类（解耦指标逻辑）"""
    def __init__(self, data, short_window=7, long_window=14, return_window=7, return_threshold=0.01,NK = 10,c = 0.07):
        self.data = data.copy()
        self.short_window = short_window
        self.long_window = long_window
        self.return_window = return_window
        self.return_threshold = return_threshold
        self.NK = NK
        self.c = c
        self.calc_indicators()

    def calc_indicators(self):
        """计算双均线和收益率指标"""
        # 计算移动平均线
        self.data["SMA_short"] = self.data["close"].rolling(window=self.short_window).mean()
        self.data["SMA_long"] = self.data["close"].rolling(window=self.long_window).mean()
        # 计算N周期收益率
        self.data["n_period_return"] = self.data["close"].pct_change(periods=self.return_window)
        self.data["n_period_return"] = self.data["n_period_return"].fillna(0)

    def Cusum_indicators(self):
        self.data["log_return"] = np.log(self.data["close"] / self.data["close"].shift(1)).fillna(0)
        self.data["cusum_pos"] = 0.0
        self.data["cusum_neg"] = 0.0
        self.data["cusum_signal"] = 0

        pos_sum = 0.0
        neg_sum = 0.0
        for i in range(1, len(self.data)):
            log_return = self.data["log_return"].iloc[i]
            pos_sum = max(0.0, pos_sum + log_return)
            neg_sum = min(0.0, neg_sum + log_return)

            if pos_sum >= self.c:
                self.data.iloc[i, self.data.columns.get_loc("cusum_signal")] = 1
                pos_sum = 0.0
                neg_sum = 0.0
            elif neg_sum <= -self.c:
                self.data.iloc[i, self.data.columns.get_loc("cusum_signal")] = -1
                pos_sum = 0.0
                neg_sum = 0.0

            self.data.iloc[i, self.data.columns.get_loc("cusum_pos")] = pos_sum
            self.data.iloc[i, self.data.columns.get_loc("cusum_neg")] = neg_sum


class CusumStrategy(BinanceUsdtSwapAccount):
    def __init__(self,data,symbol = "ETH_USDT",NK = 10,c = 0.03,init_usdt = 1000,leverage = 10,
                 take_profit_rate = 0.04, stop_loss_rate = 0.02, position_ratio = 0.1,
                 maintenance_margin_rate = 0.005):
        super().__init__()
        self.reset_account(init_usdt)
        self.leverage = leverage
        self.symbol = symbol

        self.data = data.copy()
        self.indicator = IndicatorCalculator(data, NK=NK, c=c)
        self.indicator.Cusum_indicators()
        self.data = self.indicator.data
        self.NK = NK
        self.c = c
        self.take_profit_rate = take_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.position_ratio = position_ratio
        self.maintenance_margin_rate = maintenance_margin_rate
        self.is_liquidated = False

    def _calc_trade_amt(self, price):
        max_margin = max(self.available_balance, 0.0) * self.position_ratio
        trade_value = max_margin * self.leverage
        fee = trade_value * self.trade_fee_rate
        if max_margin <= 0 or self.available_balance < max_margin + fee:
            return 0.0
        return trade_value / price

    def _calc_liquidation_price(self):
        if self.pos_status == self.POS_EMPTY or self.entry_price <= 0:
            return 0.0
        if self.pos_status == self.POS_LONG:
            return self.entry_price * (1 - 1 / self.leverage + self.maintenance_margin_rate)
        return self.entry_price * (1 + 1 / self.leverage - self.maintenance_margin_rate)

    def _liquidate_position(self, date, price):
        if self.pos_status == self.POS_EMPTY:
            return False

        pos_type = self.pos_status
        entry_price = self.entry_price
        amount = self.position_size
        close_fee = price * amount * self.trade_fee_rate
        if pos_type == self.POS_LONG:
            gross_pnl = (price - entry_price) * amount
            trade_type = "LIQUIDATE_LONG"
        else:
            gross_pnl = (entry_price - price) * amount
            trade_type = "LIQUIDATE_SHORT"

        net_pnl = gross_pnl - close_fee
        self.wallet_balance = max(0.0, self.wallet_balance + net_pnl)
        self.available_balance = self.wallet_balance
        self.initial_margin = 0.0
        self.pos_status = self.POS_EMPTY
        self.position_size = 0.0
        self.entry_price = 0.0
        self.is_liquidated = True
        self.trades.append({
            "type": trade_type,
            "date": date,
            "symbol": self.symbol,
            "price": price,
            "amount": amount,
            "fee": close_fee,
            "pnl": net_pnl,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance
        })
        print(f"{date} 触发强平，价格:{price:.2f}, 净盈亏:{net_pnl:.2f}, 钱包余额:{self.wallet_balance:.2f}")
        return True

    def _check_liquidation(self, date, price):
        if self.pos_status == self.POS_EMPTY:
            return False
        self.liq_price = self._calc_liquidation_price()
        if self.pos_status == self.POS_LONG and price <= self.liq_price:
            return self._liquidate_position(date, price)
        if self.pos_status == self.POS_SHORT and price >= self.liq_price:
            return self._liquidate_position(date, price)
        return False

    def _check_take_profit_stop_loss(self, date, price):
        if self.pos_status == self.POS_LONG:
            pnl_rate = (price - self.entry_price) / self.entry_price
            if pnl_rate <= -self.stop_loss_rate:
                success, msg, pnl = self.close_long(date, price)
                print(f"{date} 多头止损: {msg}")
                return True
            if pnl_rate >= self.take_profit_rate:
                success, msg, pnl = self.close_long(date, price)
                print(f"{date} 多头止盈: {msg}")
                return True
        elif self.pos_status == self.POS_SHORT:
            pnl_rate = (self.entry_price - price) / self.entry_price
            if pnl_rate <= -self.stop_loss_rate:
                success, msg, pnl = self.close_short(date, price)
                print(f"{date} 空头止损: {msg}")
                return True
            if pnl_rate >= self.take_profit_rate:
                success, msg, pnl = self.close_short(date, price)
                print(f"{date} 空头止盈: {msg}")
                return True
        return False

    def _open_position_by_signal(self, date, price, signal):
        trade_amt = self._calc_trade_amt(price)
        if trade_amt <= 0:
            return
        if signal == 1:
            success, msg = self.open_long(date, self.symbol, price, trade_amt)
        else:
            success, msg = self.open_short(date, self.symbol, price, trade_amt)
        print(f"{date} {msg}")

    def next(self,i):
        if self.is_liquidated or i < 1:
            return

        date = self.data.index[i]
        price = self.data["close"].iloc[i]
        signal = self.data["cusum_signal"].iloc[i]

        if self._check_liquidation(date, price):
            return

        if self._check_take_profit_stop_loss(date, price):
            return

        if signal == 1:
            if self.pos_status == self.POS_EMPTY:
                self._open_position_by_signal(date, price, signal)
            elif self.pos_status == self.POS_SHORT:
                close_success, close_msg, close_pnl = self.close_short(date, price)
                print(f"{date} CUSUM向上反手: {close_msg}")
                if close_success:
                    self._open_position_by_signal(date, price, signal)

        elif signal == -1:
            if self.pos_status == self.POS_EMPTY:
                self._open_position_by_signal(date, price, signal)
            elif self.pos_status == self.POS_LONG:
                close_success, close_msg, close_pnl = self.close_long(date, price)
                print(f"{date} CUSUM向下反手: {close_msg}")
                if close_success:
                    self._open_position_by_signal(date, price, signal)



# ========== 双均线合约策略类（核心逻辑） ==========
class DoubleMAFutureStrategy(BinanceUsdtSwapAccount):
    """双均线+动量 合约多空策略"""
    def __init__(self, data, symbol="ETH_USDT", short_window=7, long_window=14, 
                 return_window=1, return_threshold=0.005, init_usdt=1000.0, leverage=50):
        # 初始化账户
        super().__init__()
        self.reset_account(init_usdt)
        self.leverage = leverage  # 自定义杠杆
        self.symbol = symbol      # 交易对

        # 初始化数据和指标
        self.data = data.copy()
        self.indicator = IndicatorCalculator(
            data, short_window, long_window, return_window, return_threshold
        )
        self.data = self.indicator.data  # 挂载计算后的指标数据
        self.short_window = short_window
        self.long_window = long_window
        self.return_window = return_window
        self.return_threshold = return_threshold

    def next(self, i):
        """单根K线的策略逻辑（对齐现货策略逻辑）"""
        # 跳过指标未形成的阶段
        if i < max(self.short_window, self.long_window, self.return_window):
            return

        # 获取当前K线数据
        date = self.data.index[i]
        price = self.data["close"].iloc[i]
        sma_short_curr = self.data["SMA_short"].iloc[i]
        sma_long_prev = self.data["SMA_long"].iloc[i-1]
        sma_short_prev = self.data["SMA_short"].iloc[i-1]
        sma_long_curr = self.data["SMA_long"].iloc[i]
        current_return = self.data["n_period_return"].iloc[i]

        # 金叉判断（短期均线上穿长期+收益率达标）
        golden_cross = (sma_short_prev <= sma_long_prev) and (sma_short_curr > sma_long_curr)
        return_condition = current_return >= self.return_threshold

        # 死叉判断（短期均线下穿长期）
        death_cross = (sma_short_prev >= sma_long_prev) and (sma_short_curr < sma_long_curr)

        # ========== 金叉逻辑（做多） ==========
        if golden_cross and return_condition:
            # 如果当前是空仓，直接开多
            if self.pos_status == self.POS_EMPTY:
                # 计算可开仓数量（可用资金*0.95 / 价格，留5%余量）
                trade_amt = (self.available_balance * 0.95) / price
                if trade_amt > 0:
                    success, msg = self.open_long(date, self.symbol, price, trade_amt)
                    print(f"{date} {msg}")
            # 如果当前是空头，先平空再开多
            elif self.pos_status == self.POS_SHORT:
                # 平空仓
                close_success, close_msg, close_pnl = self.close_short(date, price)
                print(f"{date} {close_msg}")
                # 开多仓
                if close_success:
                    trade_amt = (self.available_balance * 0.95) / price
                    if trade_amt > 0:
                        open_success, open_msg = self.open_long(date, self.symbol, price, trade_amt)
                        print(f"{date} {open_msg}")

        # ========== 死叉逻辑（做空） ==========
        if death_cross:
            # 如果当前是空仓，直接开空
            if self.pos_status == self.POS_EMPTY:
                trade_amt = (self.available_balance * 0.95) / price
                if trade_amt > 0:
                    success, msg = self.open_short(date, self.symbol, price, trade_amt)
                    print(f"{date} {msg}")
            # 如果当前是多头，先平多再开空
            elif self.pos_status == self.POS_LONG:
                # 平多仓
                close_success, close_msg, close_pnl = self.close_long(date, price)
                print(f"{date} {close_msg}")
                # 开空仓
                if close_success:
                    trade_amt = (self.available_balance * 0.95) / price
                    if trade_amt > 0:
                        open_success, open_msg = self.open_short(date, self.symbol, price, trade_amt)
                        print(f"{date} {open_msg}")

# ========== 回测引擎（完善统计） ==========
class FutureBacktest:
    def __init__(self, strategy):
        self.strategy = strategy
        self.equity_curve = []  # 权益曲线

    def run(self):
        """运行回测"""
        data = self.strategy.data
        for i in range(len(data)):
            # 执行单K线策略逻辑
            self.strategy.next(i)
            # 计算当前总权益（钱包余额+浮动盈亏）
            unrealized_pnl = self.strategy.get_unrealized_pnl(data.index[i], data["close"].iloc[i])
            total_equity = self.strategy.wallet_balance + unrealized_pnl
            # 记录权益曲线
            self.equity_curve.append({
                "date": data.index[i],
                "equity": total_equity,
                "unrealized_pnl": unrealized_pnl,
                "wallet_balance": self.strategy.wallet_balance
            })

        # 回测结束后强制平仓
        if self.strategy.pos_status != self.strategy.POS_EMPTY:
            last_date = data.index[-1]
            last_price = data["close"].iloc[-1]
            close_success, close_msg, close_pnl = self.strategy.close_all_position(last_date, last_price)
            print(f"{last_date} 回测结束强制平仓: {close_msg}")
            # 更新最后一条权益记录
            self.equity_curve[-1]["equity"] = self.strategy.wallet_balance
            self.equity_curve[-1]["unrealized_pnl"] = 0.0

        # 转换为DataFrame方便分析
        self.equity_df = pd.DataFrame(self.equity_curve).set_index("date")
        return self.equity_df

    def calculate_stats(self):
        """计算回测统计指标"""
        if len(self.equity_df) == 0:
            return {}
        
        initial_equity = self.equity_df["equity"].iloc[0]
        final_equity = self.equity_df["equity"].iloc[-1]
        
        # 总收益率
        total_return = (final_equity - initial_equity) / initial_equity * 100
        
        # 最大回撤
        peak = self.equity_df["equity"].cummax()
        drawdown = (self.equity_df["equity"] - peak) / peak * 100
        max_drawdown = drawdown.min()
        
        # 交易统计
        trades = self.strategy.trades
        total_trades = len(trades)
        # 筛选平仓交易（计算胜率）
        close_trades = [t for t in trades if t["type"] in ["CLOSE_LONG", "CLOSE_SHORT", "LIQUIDATE_LONG", "LIQUIDATE_SHORT"]]
        win_trades = [t for t in close_trades if t["pnl"] > 0]
        win_rate = len(win_trades) / len(close_trades) * 100 if close_trades else 0
        avg_pnl = sum([t["pnl"] for t in close_trades]) / len(close_trades) if close_trades else 0
        total_fee = sum([t["fee"] for t in trades])
        
        # 输出统计结果
        print("\n========== 合约策略回测统计 ==========")
        print(f"初始资金: {initial_equity:.2f} USDT")
        print(f"最终权益: {final_equity:.2f} USDT")
        print(f"总收益率: {total_return:.2f}%")
        print(f"最大回撤: {max_drawdown:.2f}%")
        print(f"总交易次数: {total_trades} 次")
        print(f"平仓交易次数: {len(close_trades)} 次")
        print(f"胜率: {win_rate:.2f}% ({len(win_trades)}/{len(close_trades)})")
        print(f"平均每笔平仓盈亏: {avg_pnl:.2f} USDT")
        print(f"总手续费: {total_fee:.2f} USDT")
        print(f"使用杠杆: {self.strategy.leverage} 倍")
        
        return {
            "initial_equity": initial_equity,
            "final_equity": final_equity,
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "total_fee": total_fee
        }

    def plot_results(self):
        """绘制回测结果图表"""
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

        # 1. 价格+指标+交易信号
        ax1.plot(self.strategy.data.index, self.strategy.data["close"], label="Close Price", color="black", alpha=0.8)
        if "cusum_signal" in self.strategy.data.columns and hasattr(self.strategy, "c"):
            buy_signal = self.strategy.data[self.strategy.data["cusum_signal"] == 1]
            sell_signal = self.strategy.data[self.strategy.data["cusum_signal"] == -1]
            ax1.scatter(buy_signal.index, buy_signal["close"], marker='o', color='lime', label='CUSUM Up Signal', s=40, alpha=0.6)
            ax1.scatter(sell_signal.index, sell_signal["close"], marker='o', color='salmon', label='CUSUM Down Signal', s=40, alpha=0.6)
            ax1.set_title('Price & CUSUM Change Point Signals')
        elif "SMA_short" in self.strategy.data.columns and "SMA_long" in self.strategy.data.columns:
            ax1.plot(self.strategy.data.index, self.strategy.data["SMA_short"], label=f"SMA {self.strategy.short_window}", color="green", linestyle='--')
            ax1.plot(self.strategy.data.index, self.strategy.data["SMA_long"], label=f"SMA {self.strategy.long_window}", color="red", linestyle='--')
            ax1.set_title('Price & Moving Averages & Trade Signals')

        long_dates = [t["date"] for t in self.strategy.trades if t["type"] == "LONG"]
        long_prices = [t["price"] for t in self.strategy.trades if t["type"] == "LONG"]
        short_dates = [t["date"] for t in self.strategy.trades if t["type"] == "SHORT"]
        short_prices = [t["price"] for t in self.strategy.trades if t["type"] == "SHORT"]
        close_dates = [t["date"] for t in self.strategy.trades if t["type"] in ["CLOSE_LONG", "CLOSE_SHORT"]]
        close_prices = [t["price"] for t in self.strategy.trades if t["type"] in ["CLOSE_LONG", "CLOSE_SHORT"]]
        liquidation_dates = [t["date"] for t in self.strategy.trades if t["type"] in ["LIQUIDATE_LONG", "LIQUIDATE_SHORT"]]
        liquidation_prices = [t["price"] for t in self.strategy.trades if t["type"] in ["LIQUIDATE_LONG", "LIQUIDATE_SHORT"]]

        ax1.scatter(long_dates, long_prices, marker='^', color='green', label='Long Entry', s=100)
        ax1.scatter(short_dates, short_prices, marker='v', color='red', label='Short Entry', s=100)
        ax1.scatter(close_dates, close_prices, marker='x', color='blue', label='Close', s=80)
        ax1.scatter(liquidation_dates, liquidation_prices, marker='X', color='purple', label='Liquidation', s=120)
        ax1.legend()
        ax1.grid(True)

        # 2. 权益曲线
        ax2.plot(self.equity_df.index, self.equity_df["equity"], label='Equity Curve', color='blue')
        ax2.fill_between(self.equity_df.index, self.equity_df["equity"], alpha=0.2)
        ax2.set_title('Equity Curve (Wallet + Unrealized PnL)')
        ax2.legend()
        ax2.grid(True)

        # 3. 策略指标
        if "cusum_pos" in self.strategy.data.columns and "cusum_neg" in self.strategy.data.columns and hasattr(self.strategy, "c"):
            ax3.plot(self.strategy.data.index, self.strategy.data["cusum_pos"], label='CUSUM Positive Sum', color='green')
            ax3.plot(self.strategy.data.index, self.strategy.data["cusum_neg"], label='CUSUM Negative Sum', color='red')
            ax3.axhline(y=self.strategy.c, color='green', linestyle='--', label=f'Upper Threshold {self.strategy.c:.2%}')
            ax3.axhline(y=-self.strategy.c, color='red', linestyle='--', label=f'Lower Threshold {-self.strategy.c:.2%}')
            ax3.set_title('CUSUM Change Point Indicator')
            ax3.set_ylabel('Cumulative Log Return')
        elif "n_period_return" in self.strategy.data.columns and hasattr(self.strategy, "return_threshold"):
            ax3.plot(self.strategy.data.index, self.strategy.data["n_period_return"], label=f'{self.strategy.return_window}-Period Return', color='orange')
            ax3.axhline(y=self.strategy.return_threshold, color='red', linestyle='--', label=f'Return Threshold ({self.strategy.return_threshold:.1%})')
            ax3.set_title(f'{self.strategy.return_window}-Period Return')
            ax3.set_ylabel('Return')
        ax3.legend()
        ax3.grid(True)

        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    data_loader = DataLoader()
    data = data_loader.get_data_from_csv()

    strategy = CusumStrategy(
        data=data,
        symbol="ETH_USDT",
        NK=14,
        c=0.07,
        init_usdt=10000.0,
        leverage=10,
        take_profit_rate=0.018,
        stop_loss_rate=0.033,
        position_ratio=0.3,
        maintenance_margin_rate=0.005
    )

    backtest = FutureBacktest(strategy)
    equity_df = backtest.run()

    stats = backtest.calculate_stats()

    backtest.plot_results()