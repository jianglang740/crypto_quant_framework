from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from crypto_quant.enums import MarginMode, TradingMode


@dataclass(slots=True)
class BinanceConfig:
    api_key: str = ""
    secret: str = ""
    password: str | None = None
    trading_mode: TradingMode = TradingMode.SPOT
    enable_rate_limit: bool = True
    sandbox: bool = False
    timeout: int = 30_000
    options: dict[str, Any] = field(default_factory=dict)
    proxies: dict[str, str] | None = None

    def ccxt_options(self) -> dict[str, Any]:
        default_type = "spot" if self.trading_mode == TradingMode.SPOT else "future"
        options = {"defaultType": default_type, **self.options}
        config: dict[str, Any] = {
            "apiKey": self.api_key,
            "secret": self.secret,
            "enableRateLimit": self.enable_rate_limit,
            "timeout": self.timeout,
            "options": options,
        }
        if self.password:
            config["password"] = self.password
        if self.proxies:
            config["proxies"] = self.proxies
        return config


@dataclass(slots=True)
class MySQLConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: str = "crypto_quant"
    charset: str = "utf8mb4"
    echo: bool = False

    @property
    def url(self) -> str:
        return (
            f"mysql+pymysql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )


@dataclass(slots=True)
class BacktestConfig:
    initial_cash: Decimal = Decimal("10000")
    commission_rate: Decimal = Decimal("0.0004")
    slippage_rate: Decimal = Decimal("0")
    allow_short: bool = True
    leverage: Decimal = Decimal("1")
    margin_mode: MarginMode = MarginMode.CROSS
    maintenance_margin_rate: Decimal = Decimal("0.005")
    liquidation_fee_rate: Decimal = Decimal("0.001")


@dataclass(slots=True)
class LiveConfig:
    dry_run: bool = True
    poll_interval_seconds: float = 3.0
    max_order_retries: int = 3
    initial_cash: Decimal = Decimal("10000")
    commission_rate: Decimal = Decimal("0.0004")
    slippage_rate: Decimal = Decimal("0")
    leverage: Decimal = Decimal("1")
    maintenance_margin_rate: Decimal = Decimal("0.005")
    sync_on_start: bool = True
    sync_interval_seconds: float = 30.0
    sync_symbols: list[str] = field(default_factory=list)
    account_quote_asset: str = "USDT"


@dataclass(slots=True)
class FrameworkConfig:
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    live: LiveConfig = field(default_factory=LiveConfig)
