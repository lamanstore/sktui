"""Domain models and data structures for SKTUI."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class Scrip:
    scrip_code: int | None
    trading_symbol: str
    exchange: str = "NC"
    company_name: str = ""
    inst_type: str = "EQ"
    lot_size: int = 1
    tick_size: float = 0.05
    expiry: str = ""
    strike: float = 0.0
    option_type: str = ""

    def feed_key(self) -> str:
        return f"{self.exchange}{self.scrip_code}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scripCode": self.scrip_code,
            "tradingSymbol": self.trading_symbol,
            "exchange": self.exchange,
            "companyName": self.company_name,
            "instType": self.inst_type,
            "lotSize": self.lot_size,
            "tickSize": self.tick_size,
            "expiry": self.expiry,
            "strike": self.strike,
            "optionType": self.option_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Scrip:
        return cls(
            scrip_code=d.get("scripCode"),
            trading_symbol=d.get("tradingSymbol", ""),
            exchange=d.get("exchange", "NC"),
            company_name=d.get("companyName", ""),
            inst_type=d.get("instType", "EQ"),
            lot_size=int(d.get("lotSize") or 1),
            tick_size=float(d.get("tickSize") or 0.05),
            expiry=d.get("expiry", ""),
            strike=float(d.get("strike") or 0.0),
            option_type=d.get("optionType", ""),
        )


@dataclass
class Tick:
    scrip_code: int | None
    exchange: str
    ltp: float
    rs_change: float = 0.0
    per_change: float = 0.0
    bid_price: float = 0.0
    off_price: float = 0.0
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    current_oi: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def key(self) -> str:
        return f"{self.exchange}{self.scrip_code}"


@dataclass
class Order:
    order_id: str
    scrip_code: int | None
    trading_symbol: str
    exchange: str
    buy_sell: Literal["B", "S"]
    order_qty: int
    exec_qty: int
    order_price: str
    exec_price: str
    order_status: str
    request_status: str
    price_type: str = "NORMAL"
    product_type: str = "INVESTMENT"
    last_mod_time: str = ""
    rms_code: str = "ANY"
    error_msg: str = ""


@dataclass
class Position:
    trading_symbol: str
    exchange: str
    product_type: str
    buy_qty: int
    buy_rate: float
    sell_qty: int
    sell_rate: float
    net_qty: int
    avg_price: float
    bpl: float = 0.0
    mtm: float = 0.0
    scrip_code: int | None = None


@dataclass
class Holding:
    trading_symbol: str
    exchange: str
    available_qty: int
    cnc_qty: int = 0
    invest_qty: int = 0
    hold_price: float = 0.0
    dp: int = 0
    pledge: int = 0
    mf: int = 0
    receivable: int = 0
    trading_allowed: str = "Y"
    scrip_code: int | None = None
