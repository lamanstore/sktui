"""Automated Execution & Hummingbot Bot Orchestration Engine for SKTUI.

Implements Milestone 5 (R5):
- Deterministic BotState machine lifecycle (INIT, CONFIGURED, RUNNING, PAUSED, STOPPED, ERROR)
- Pure Market Making (PMM) with Avellaneda-Stoikov inventory skewing
- Pair statistical arbitrage order intent generation
- Momentum and predictor strategy handlers
- Pre-trade risk validation and order size limits
- Daily drawdown circuit breaker lockout
- Emergency panic killswitch (CANCEL_ALL and FLATTEN_ALL)
- Telemetry reporting and multi-bot fleet orchestration (BotManager)
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from enum import Enum
from typing import Any


class BotState(str, Enum):
    """Lifecycle states for automated bot instances."""
    INIT = "INIT"
    CONFIGURED = "CONFIGURED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class StrategyType(str, Enum):
    """Supported trading bot strategy archetypes."""
    PMM = "pmm"
    ARBITRAGE = "arbitrage"
    MOMENTUM = "momentum"
    PREDICTOR = "predictor"


class PanicMode(str, Enum):
    """Emergency killswitch action modes."""
    CANCEL_ALL = "CANCEL_ALL"
    FLATTEN_ALL = "FLATTEN_ALL"


class BotInstance:
    """An autonomous trading bot executing a designated strategy."""

    def __init__(
        self,
        strategy: str,
        symbol: str,
        client: Any = None,
        paper: bool = True,
        capital: float = 100_000.0,
        parameters: dict[str, Any] | None = None,
        bot_id: str | None = None,
        name: str | None = None,
    ) -> None:
        self.strategy = (strategy or "pmm").strip().lower()
        self.symbol = (symbol or "").strip().upper()
        self.client = client
        self.paper = paper
        self.capital = float(capital)
        self.parameters = dict(parameters) if parameters else {}
        self.bot_id = bot_id or f"bot_{self.strategy}_{self.symbol.replace(',', '_').replace('/', '_')}_{uuid.uuid4().hex[:8]}"
        self.name = name or f"{self.strategy.upper()} [{self.symbol}]"

        # Lifecycle State
        self.state: BotState = BotState.CONFIGURED if parameters else BotState.INIT
        self.start_time: float | None = None
        self.stop_time: float | None = None
        self.paused_duration: float = 0.0
        self._last_pause_time: float | None = None

        # Execution, PnL & Order Tracking
        self.total_orders: int = 0
        self.filled_orders: int = 0
        self.cancelled_orders: int = 0
        self.pnl: float = 0.0
        self.daily_pnl: float = 0.0
        self.inventory: float = 0.0
        self.active_orders: list[dict[str, Any]] = []
        self.last_error: str | None = None

    # ── State Machine Lifecycle ───────────────────────────────────────────────

    def start(self) -> bool:
        """Transition from INIT or CONFIGURED to RUNNING. Idempotent if RUNNING."""
        if self.state in (BotState.STOPPED, BotState.ERROR):
            return False
        if self.state == BotState.RUNNING:
            return True
        self.state = BotState.RUNNING
        if self.start_time is None:
            self.start_time = time.time()
        return True

    def pause(self) -> bool:
        """Transition from RUNNING to PAUSED. Rejected from other states."""
        if self.state != BotState.RUNNING:
            return False
        self.state = BotState.PAUSED
        self._last_pause_time = time.time()
        return True

    def resume(self) -> bool:
        """Transition from PAUSED to RUNNING. Rejected from INIT, STOPPED, or ERROR."""
        if self.state != BotState.PAUSED:
            return False
        self.state = BotState.RUNNING
        if self._last_pause_time is not None:
            self.paused_duration += max(0.0, time.time() - self._last_pause_time)
            self._last_pause_time = None
        return True

    def stop(self) -> bool:
        """Transition from any state to STOPPED (terminal lifecycle state)."""
        if self.state == BotState.STOPPED:
            return True
        self.state = BotState.STOPPED
        self.stop_time = time.time()
        return True

    # ── Strategy: Pure Market Making (PMM) ────────────────────────────────────

    def calculate_quotes(self, mid_price: float, inventory: int | float = 0) -> tuple[float, float]:
        """Calculate bid and ask quotes with inventory reservation price skewing.

        Neutral inventory (0): bid < mid_price < ask
        Positive inventory (> 0, long): lower reservation price -> ask_long <= ask_neutral & bid_long <= bid_neutral
        Negative inventory (< 0, short): higher reservation price -> ask_short >= ask_neutral & bid_short >= bid_neutral
        """
        if mid_price <= 0:
            return (0.0, 0.0)

        spread_bps = float(self.parameters.get("spread_bps", 20.0))
        inventory_skew_enabled = bool(self.parameters.get("inventory_skew", True))
        half_spread = mid_price * (spread_bps / 10000.0) / 2.0
        if half_spread <= 0:
            half_spread = 0.05

        skew = 0.0
        if inventory_skew_enabled and inventory != 0:
            # Positive inventory produces positive skew, shifting reservation price downward
            skew = (float(inventory) / 50.0) * (half_spread * 0.20)

        reservation_price = mid_price - skew
        bid_price = round(reservation_price - half_spread, 2)
        ask_price = round(reservation_price + half_spread, 2)
        return (bid_price, ask_price)

    def calculate_quotes_from_depth(self, depth: dict[str, Any]) -> tuple[float, float] | dict[str, Any] | None:
        """Derive quotes from order book depth with zero-division and empty-book safety."""
        if not depth or not isinstance(depth, dict):
            return None

        bids = depth.get("bids") or []
        asks = depth.get("asks") or []
        if not bids or not asks:
            return None

        def _extract_px(item: Any) -> float:
            if isinstance(item, (list, tuple)) and len(item) > 0:
                return float(item[0])
            if isinstance(item, dict):
                return float(item.get("price") or item.get("rate") or 0.0)
            return float(item)

        try:
            best_bid = _extract_px(bids[0])
            best_ask = _extract_px(asks[0])
            if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
                return None
            mid_price = (best_bid + best_ask) / 2.0
            if mid_price <= 0:
                return None
            return self.calculate_quotes(mid_price=mid_price, inventory=self.inventory)
        except (IndexError, TypeError, ValueError, ZeroDivisionError):
            return None

    # ── Strategy: Statistical Arbitrage ───────────────────────────────────────

    def process_spread_tick(self, zscore: float, price_a: float, price_b: float) -> list[dict[str, Any]] | None:
        """Process spread Z-score and generate paired hedged order intents on threshold breach."""
        if not math.isfinite(zscore) or price_a <= 0 or price_b <= 0:
            return []

        entry_zscore = float(self.parameters.get("entry_zscore", 2.0))
        exit_zscore = float(self.parameters.get("exit_zscore", 0.5))
        order_amount = int(self.parameters.get("order_amount", 10))

        # Parse symbol pair: e.g. "HDFCBANK,ICICIBANK" or "HDFCBANK/ICICIBANK"
        syms = [s.strip() for s in self.symbol.replace("/", ",").replace("-", ",").split(",") if s.strip()]
        sym_a = syms[0] if len(syms) > 0 else "LEG_A"
        sym_b = syms[1] if len(syms) > 1 else "LEG_B"

        if zscore >= entry_zscore:
            # Spread is elevated (A is overpriced relative to B): Sell A, Buy B
            order_a = {"symbol": sym_a, "action": "SELL", "qty": order_amount, "price": price_a, "leg": "A", "zscore": zscore}
            order_b = {"symbol": sym_b, "action": "BUY", "qty": order_amount, "price": price_b, "leg": "B", "zscore": zscore}
            return [order_a, order_b]
        elif zscore <= -entry_zscore:
            # Spread is depressed (A is underpriced relative to B): Buy A, Sell B
            order_a = {"symbol": sym_a, "action": "BUY", "qty": order_amount, "price": price_a, "leg": "A", "zscore": zscore}
            order_b = {"symbol": sym_b, "action": "SELL", "qty": order_amount, "price": price_b, "leg": "B", "zscore": zscore}
            return [order_a, order_b]
        elif abs(zscore) <= exit_zscore:
            # Mean reversion target reached
            return []
        return []

    # ── Strategy: Momentum & Predictor Handlers ───────────────────────────────

    def process_signal(self, signal: Any, current_price: float) -> list[dict[str, Any]]:
        """Process momentum or technical composite signal into order intents."""
        if self.state != BotState.RUNNING or current_price <= 0:
            return []

        sig_type = getattr(signal, "signal_type", str(signal)).upper()
        order_qty = int(self.parameters.get("order_amount", 10))
        sl = getattr(signal, "stop_loss", self.parameters.get("stop_loss", 0.0))
        tp = getattr(signal, "take_profit", self.parameters.get("take_profit", 0.0))

        if "BUY" in sig_type:
            return [{
                "symbol": self.symbol,
                "action": "BUY",
                "qty": order_qty,
                "price": current_price,
                "stop_loss": sl,
                "take_profit": tp,
            }]
        elif "SELL" in sig_type:
            return [{
                "symbol": self.symbol,
                "action": "SELL",
                "qty": order_qty,
                "price": current_price,
                "stop_loss": sl,
                "take_profit": tp,
            }]
        return []

    def process_prediction(self, predicted_return: float, confidence: float, current_price: float) -> list[dict[str, Any]]:
        """Process AI predictor return forecast with confidence-scaled sizing."""
        if self.state != BotState.RUNNING or not math.isfinite(predicted_return) or not math.isfinite(confidence) or current_price <= 0:
            return []

        min_confidence = float(self.parameters.get("min_confidence", 55.0))
        ret_thresh = float(self.parameters.get("return_threshold", 0.002))
        base_qty = int(self.parameters.get("order_amount", 10))

        if confidence >= min_confidence:
            scale = min(3.0, max(1.0, confidence / 50.0))
            qty = max(1, int(base_qty * scale))
            if predicted_return >= ret_thresh:
                return [{"symbol": self.symbol, "action": "BUY", "qty": qty, "price": current_price, "confidence": confidence}]
            elif predicted_return <= -ret_thresh:
                return [{"symbol": self.symbol, "action": "SELL", "qty": qty, "price": current_price, "confidence": confidence}]
        return []

    # ── Pre-Trade Risk Engine & Order Execution ───────────────────────────────

    def submit_order(self, symbol: str, qty: int | float, price: float, action: str) -> tuple[bool, str | dict[str, Any]]:
        """Validate order against pre-trade risk controls and submit to client or simulator."""
        if self.state != BotState.RUNNING:
            return False, f"Pre-trade rejection: Bot is in {self.state.value} state"

        if qty <= 0:
            return False, "Risk rejection: order quantity must be positive"
        if price < 0 or not math.isfinite(price):
            return False, "Risk rejection: order price must be non-negative and finite"

        order_val = float(qty) * float(price)
        max_order_val = self.parameters.get("max_order_val")
        if max_order_val is not None and order_val > float(max_order_val):
            return False, f"Risk limit exceeded: order value ₹{order_val:,.2f} exceeds limit ₹{float(max_order_val):,.2f}"

        side = "B" if str(action).upper().startswith("B") else "S"
        order_params = {
            "requestType": "NEW",
            "exchange": self.parameters.get("exchange", "NC"),
            "tradingSymbol": symbol.strip().upper(),
            "quantity": int(qty),
            "price": str(price),
            "orderType": "NORMAL" if price > 0 else "MKT",
            "transactionType": side,
            "productType": self.parameters.get("product_type", "INVESTMENT"),
        }

        self.total_orders += 1

        if self.client and hasattr(self.client, "submit"):
            res = self.client.submit(order_params)
            self.filled_orders += 1
            ord_id = str(res.get("order_id") or res.get("orderId") or self.total_orders)
            order_record = {
                "order_id": ord_id,
                "symbol": symbol.strip().upper(),
                "qty": int(qty),
                "price": float(price),
                "action": side,
                "status": "FILLED",
                "timestamp": time.time(),
            }
            self.active_orders.append(order_record)
            return True, res

        # Paper simulation fallback
        self.filled_orders += 1
        sim_res = {
            "order_id": f"sim_{self.total_orders}",
            "symbol": symbol.strip().upper(),
            "quantity": int(qty),
            "price": float(price),
            "transactionType": side,
            "status": "FILLED",
            "timestamp": time.time(),
        }
        self.active_orders.append(sim_res)
        return True, sim_res

    # ── PnL & Daily Drawdown Circuit Breaker ───────────────────────────────────

    def record_pnl(self, delta_pnl: float) -> None:
        """Record real-time PnL delta and trip circuit breaker lockout if daily limit is breached."""
        delta = float(delta_pnl)
        self.pnl += delta
        self.daily_pnl += delta

        daily_loss_limit = self.parameters.get("daily_loss_limit")
        if daily_loss_limit is not None and float(daily_loss_limit) > 0:
            limit = float(daily_loss_limit)
            if self.daily_pnl <= -abs(limit):
                self.state = BotState.STOPPED
                self.last_error = f"Circuit breaker tripped: daily loss ₹{self.daily_pnl:,.2f} breached limit ₹{limit:,.2f}"
                # Cancel open orders upon circuit breaker breach
                if self.client and hasattr(self.client, "cancel_by_id"):
                    for ord_info in list(self.active_orders):
                        oid = ord_info.get("order_id") or ord_info.get("orderId")
                        if oid:
                            try:
                                self.client.cancel_by_id(oid)
                            except Exception:
                                pass
                self.cancelled_orders += len(self.active_orders)
                self.active_orders.clear()

    # ── Emergency Panic Killswitch ────────────────────────────────────────────

    def emergency_panic(self, mode: str = "CANCEL_ALL") -> dict[str, Any]:
        """Emergency killswitch: cancel all active orders and optionally flatten open positions."""
        mode_upper = mode.upper()
        cancelled_count = 0
        flattened_count = 0

        # 1. Cancel open orders
        if self.client and hasattr(self.client, "cancel_by_id"):
            for ord_info in list(self.active_orders):
                oid = ord_info.get("order_id") or ord_info.get("orderId")
                if oid:
                    try:
                        self.client.cancel_by_id(oid)
                        cancelled_count += 1
                    except Exception:
                        pass
        cancelled_count = max(cancelled_count, len(self.active_orders))
        self.cancelled_orders += cancelled_count
        self.active_orders.clear()

        # 2. Flatten open positions if requested
        if mode_upper == "FLATTEN_ALL":
            if self.client and hasattr(self.client, "positions"):
                try:
                    open_pos = self.client.positions()
                    for p in open_pos:
                        net_qty = int(p.get("net_qty") or p.get("netQty") or 0)
                        sym = str(p.get("trading_symbol") or p.get("tradingSymbol") or self.symbol)
                        if net_qty != 0:
                            side = "S" if net_qty > 0 else "B"
                            if hasattr(self.client, "submit"):
                                self.client.submit({
                                    "requestType": "NEW",
                                    "exchange": "NC",
                                    "tradingSymbol": sym,
                                    "quantity": abs(net_qty),
                                    "price": "0",
                                    "orderType": "MKT",
                                    "transactionType": side,
                                    "productType": "CNF",
                                })
                                flattened_count += 1
                except Exception:
                    pass

        self.state = BotState.STOPPED
        self.stop_time = time.time()
        return {
            "status": "PANIC_EXECUTED",
            "bot_id": self.bot_id,
            "mode": mode_upper,
            "cancelled_orders": cancelled_count,
            "flattened_positions": flattened_count,
            "timestamp": time.time(),
        }

    # ── Telemetry & Metrics ───────────────────────────────────────────────────

    def get_telemetry(self) -> dict[str, Any]:
        """Return standardized telemetry snapshot with finite numerical guarantees."""
        now = time.time()
        uptime = 0.0
        if self.start_time is not None:
            if self.state == BotState.RUNNING:
                uptime = max(0.0, now - self.start_time - self.paused_duration)
            elif self.stop_time is not None:
                uptime = max(0.0, self.stop_time - self.start_time - self.paused_duration)
            else:
                uptime = max(0.0, now - self.start_time - self.paused_duration)

        return {
            "bot_id": self.bot_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "state": self.state.value if hasattr(self.state, "value") else str(self.state),
            "paper": self.paper,
            "uptime_seconds": float(uptime) if math.isfinite(uptime) else 0.0,
            "total_orders": int(self.total_orders),
            "filled_orders": int(self.filled_orders),
            "cancelled_orders": int(self.cancelled_orders),
            "pnl": float(self.pnl) if math.isfinite(self.pnl) else 0.0,
            "daily_pnl": float(self.daily_pnl) if math.isfinite(self.daily_pnl) else 0.0,
            "inventory": float(self.inventory) if math.isfinite(self.inventory) else 0.0,
            "daily_loss_limit": float(self.parameters.get("daily_loss_limit", 5000.0)),
            "max_order_val": float(self.parameters.get("max_order_val", 50000.0)),
        }


class BotManager:
    """Multi-bot fleet coordinator managing registries, batch controls, and telemetry."""

    _instance: "BotManager | None" = None
    _singleton_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "BotManager":
        """Thread-safe singleton accessor."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for test isolation)."""
        with cls._singleton_lock:
            cls._instance = None

    def __init__(self) -> None:
        self._bots: dict[str, BotInstance] = {}
        self._lock = threading.RLock()

    def register(self, bot: BotInstance, bot_id: str | None = None) -> str:
        """Register a BotInstance in the registry."""
        with self._lock:
            b_id = bot_id or bot.bot_id
            bot.bot_id = b_id
            self._bots[b_id] = bot
            return b_id

    def register_bot(self, bot: BotInstance, bot_id: str | None = None) -> str:
        """Alias for register()."""
        return self.register(bot, bot_id)

    def unregister(self, bot_id: str) -> BotInstance | None:
        """Remove a bot from the registry, stopping it if running."""
        with self._lock:
            bot = self._bots.get(bot_id)
            if bot:
                if bot.state == BotState.RUNNING:
                    bot.stop()
                del self._bots[bot_id]
            return bot

    def unregister_bot(self, bot_id: str) -> BotInstance | None:
        """Alias for unregister()."""
        return self.unregister(bot_id)

    def get_bot(self, bot_id: str) -> BotInstance | None:
        """Retrieve a bot by ID."""
        with self._lock:
            return self._bots.get(bot_id)

    def list_bots(self) -> list[BotInstance]:
        """Return all registered bots."""
        with self._lock:
            return list(self._bots.values())

    def create_bot(
        self,
        strategy: str,
        symbol: str,
        client: Any = None,
        paper: bool = True,
        capital: float = 100_000.0,
        parameters: dict[str, Any] | None = None,
        bot_id: str | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> BotInstance:
        """Factory method to instantiate, register, and return a BotInstance."""
        bot = BotInstance(
            strategy=strategy,
            symbol=symbol,
            client=client,
            paper=paper,
            capital=capital,
            parameters=parameters,
            bot_id=bot_id,
            name=name,
            **kwargs,
        )
        self.register(bot, bot.bot_id)
        return bot

    def start_all(self) -> dict[str, bool]:
        """Start all registered bots."""
        with self._lock:
            return {b_id: bot.start() for b_id, bot in self._bots.items()}

    def stop_all(self) -> dict[str, bool]:
        """Stop all registered bots."""
        with self._lock:
            return {b_id: bot.stop() for b_id, bot in self._bots.items()}

    def pause_all(self) -> dict[str, bool]:
        """Pause all running bots."""
        with self._lock:
            return {b_id: bot.pause() for b_id, bot in self._bots.items()}

    def resume_all(self) -> dict[str, bool]:
        """Resume all paused bots."""
        with self._lock:
            return {b_id: bot.resume() for b_id, bot in self._bots.items()}

    def emergency_panic_all(self, mode: str = "CANCEL_ALL") -> dict[str, dict[str, Any]]:
        """Trigger emergency killswitch across all registered bots."""
        with self._lock:
            return {b_id: bot.emergency_panic(mode=mode) for b_id, bot in self._bots.items()}

    def panic_all(self, mode: str = "CANCEL_ALL") -> dict[str, dict[str, Any]]:
        """Alias for emergency_panic_all()."""
        return self.emergency_panic_all(mode=mode)

    def get_aggregated_telemetry(self) -> dict[str, Any]:
        """Compute aggregated telemetry metrics across all managed bots."""
        with self._lock:
            total_bots = len(self._bots)
            running_bots = sum(1 for b in self._bots.values() if b.state == BotState.RUNNING)
            paused_bots = sum(1 for b in self._bots.values() if b.state == BotState.PAUSED)
            stopped_bots = sum(1 for b in self._bots.values() if b.state == BotState.STOPPED)
            error_bots = sum(1 for b in self._bots.values() if b.state == BotState.ERROR)

            total_orders = sum(b.total_orders for b in self._bots.values())
            filled_orders = sum(b.filled_orders for b in self._bots.values())
            total_pnl = sum(b.pnl for b in self._bots.values())

            return {
                "total_bots": total_bots,
                "running_bots": running_bots,
                "paused_bots": paused_bots,
                "stopped_bots": stopped_bots,
                "error_bots": error_bots,
                "total_orders": total_orders,
                "filled_orders": filled_orders,
                "total_pnl": float(total_pnl) if math.isfinite(total_pnl) else 0.0,
                "bots": {b_id: b.get_telemetry() for b_id, b in self._bots.items()},
            }
