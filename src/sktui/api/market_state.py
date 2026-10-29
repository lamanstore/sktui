"""MarketState and SymbolState models, normalization, and subscription manager."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sktui.utils import safe_float


def normalize_tick(raw_tick: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw WebSocket feed message or REST quote into standard tick dictionary."""
    data = raw_tick.get("data") if isinstance(raw_tick.get("data"), dict) else raw_tick
    c = dict(data)
    
    # Map field variants
    field_mappings = [
        ("ltp",       ("lastTradedPrice", "LTP", "price")),
        ("rsChange",  ("change", "netPriceChange", "chg")),
        ("perChange", ("pChange", "percentChange", "pct")),
        ("bidPrice",  ("bid", "buyPrice")),
        ("offPrice",  ("ask", "sellPrice")),
        ("bidQty",    ("bQty", "buyQty")),
        ("offQty",    ("aQty", "sellQty")),
        ("open",      ("openPrice", "open_price")),
        ("high",      ("highPrice", "high_price")),
        ("low",       ("lowPrice", "low_price")),
        ("close",     ("closePrice", "close_price")),
        ("qty",       ("volume", "vol")),
        ("currentOI", ("openInterest", "oi")),
    ]
    for dst, srcs in field_mappings:
        if dst not in c or c[dst] is None:
            for src in srcs:
                if src in c and c[src] is not None:
                    c[dst] = c[src]
                    break
    return c


@dataclass
class SymbolState:
    """Normalized live quote state for an individual market instrument."""
    exchange: str = "NC"
    scrip_code: int | str = 0
    trading_symbol: str = ""
    last_price: float = 0.0
    prev_price: float = 0.0
    change: float = 0.0
    pct: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    volume: int = 0
    oi: int = 0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)
    is_stale: bool = False

    @property
    def key(self) -> str:
        return f"{self.exchange}{self.scrip_code}"

    def update_from_tick(self, tick: dict[str, Any]) -> None:
        """Update fields from a normalized tick dictionary."""
        norm = normalize_tick(tick)
        new_ltp = safe_float(norm.get("ltp"))
        if new_ltp > 0:
            if self.last_price > 0:
                self.prev_price = self.last_price
            self.last_price = new_ltp

        if norm.get("rsChange") is not None:
            self.change = safe_float(norm.get("rsChange"))
        if norm.get("perChange") is not None:
            self.pct = safe_float(norm.get("perChange"))
        if norm.get("bidPrice") is not None:
            self.bid = safe_float(norm.get("bidPrice"))
        if norm.get("offPrice") is not None:
            self.ask = safe_float(norm.get("offPrice"))
        if norm.get("bidQty") is not None:
            self.bid_qty = int(safe_float(norm.get("bidQty")))
        if norm.get("offQty") is not None:
            self.ask_qty = int(safe_float(norm.get("offQty")))
        if norm.get("qty") is not None:
            self.volume = int(safe_float(norm.get("qty")))
        if norm.get("currentOI") is not None:
            self.oi = int(safe_float(norm.get("currentOI")))
        if norm.get("open") is not None:
            self.open_price = safe_float(norm.get("open"))
        if norm.get("high") is not None:
            self.high_price = safe_float(norm.get("high"))
        if norm.get("low") is not None:
            self.low_price = safe_float(norm.get("low"))
        if norm.get("close") is not None:
            self.close_price = safe_float(norm.get("close"))

        if norm.get("tradingSymbol"):
            self.trading_symbol = str(norm["tradingSymbol"])
        if norm.get("exchange"):
            self.exchange = str(norm["exchange"])
        elif norm.get("exchangeCode"):
            self.exchange = str(norm["exchangeCode"])

        self.timestamp = time.monotonic()
        self.is_stale = False

    def to_dict(self) -> dict[str, Any]:
        """Convert state to a dictionary compatible with legacy UI widgets."""
        return {
            "exchange": self.exchange,
            "scripCode": self.scrip_code,
            "tradingSymbol": self.trading_symbol,
            "ltp": self.last_price,
            "rsChange": self.change,
            "perChange": self.pct,
            "bidPrice": self.bid,
            "offPrice": self.ask,
            "bidQty": self.bid_qty,
            "offQty": self.ask_qty,
            "qty": self.volume,
            "currentOI": self.oi,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "is_stale": self.is_stale,
            "timestamp": self.timestamp,
        }


class MarketState:
    """Central market state store tracking all live symbol states and ticks."""

    def __init__(self) -> None:
        self.symbols: dict[str, SymbolState] = {}
        self.feed_state: str = "CONNECTED"
        self.last_latency_ms: float = 15.0

    def get_or_create(self, exchange: str, scrip_code: int | str, symbol: str = "") -> SymbolState:
        key = f"{exchange}{scrip_code}"
        if key not in self.symbols:
            self.symbols[key] = SymbolState(
                exchange=exchange,
                scrip_code=scrip_code,
                trading_symbol=symbol,
            )
        return self.symbols[key]

    def update_tick(self, raw_tick: dict[str, Any]) -> SymbolState | None:
        """Ingest raw feed tick, update normalized symbol state, and return SymbolState."""
        norm = normalize_tick(raw_tick)
        scrip = norm.get("scripCode")
        exch = norm.get("exchangeCode") or norm.get("exchange", "NC")
        if not scrip:
            return None
        sym = norm.get("tradingSymbol", "")
        st = self.get_or_create(exch, scrip, sym)
        st.update_from_tick(norm)
        return st

    def get(self, key: str) -> SymbolState | None:
        return self.symbols.get(key)

    def is_stale(self, key: str, threshold: float = 10.0) -> bool:
        st = self.symbols.get(key)
        if not st:
            return True
        return (time.monotonic() - st.timestamp) > threshold


class SubscriptionManager:
    """Manages live WebSocket feed subscription keys and reconnection resubscribe."""

    def __init__(self, get_feed: Callable[[], Any] | None = None) -> None:
        self._keys: set[str] = set()
        self._get_feed = get_feed

    def add(self, key: str) -> None:
        self._keys.add(key)
        feed = self._get_feed() if self._get_feed else None
        if feed and getattr(feed, "ready", False):
            feed.subscribe(key)

    def remove(self, key: str) -> None:
        self._keys.discard(key)
        feed = self._get_feed() if self._get_feed else None
        if feed and getattr(feed, "ready", False):
            feed.unsubscribe(key)

    def keys(self) -> list[str]:
        return sorted(self._keys)

    def resubscribe(self) -> None:
        feed = self._get_feed() if self._get_feed else None
        if feed and getattr(feed, "ready", False):
            for k in self.keys():
                feed.subscribe(k)
