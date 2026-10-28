"""Order service — open_ticket, risk check, confirm flow, submit and cancel orchestration.

This service is the single place screens call when they want to trade.
It enforces pre-trade risk controls, logs execution audit events,
and coordinates with the REST API client.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from sktui.services.audit import audit_trail
from sktui.services.risk_engine import RiskEngine
from sktui.state.order_store import OrderStore
from sktui.utils import build_order, get, is_open_order, order_summary

if TYPE_CHECKING:
    from sktui.api.client import Client


class OrderService:
    """Orchestrates the full order flow: ticket -> risk check -> confirm -> submit / cancel."""

    def __init__(
        self,
        client: "Client",
        risk_engine: RiskEngine | None = None,
        order_store: OrderStore | None = None,
    ) -> None:
        self._client = client
        self.risk_engine = risk_engine or RiskEngine()
        self.order_store = order_store or OrderStore()

    @property
    def client(self) -> "Client":
        return self._client

    def open_ticket(
        self,
        screen: Any,
        info: dict,
        mode: str,
        on_activity: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Push an OrderTicket modal onto *screen*'s app, handle the result with pre-trade risk check."""
        from sktui.screens.modals import OrderTicket

        # Pre-ticket validation check before opening dialog
        sym = str(info.get("tradingSymbol", ""))
        positions = getattr(screen, "positions", [])
        ok, pre_err = self.risk_engine.check_pre_ticket(sym, positions)
        if not ok:
            screen.app.notify(f"⛔ Risk Pre-Check Blocked:\n{pre_err}", severity="error", timeout=10)
            if on_activity:
                on_activity(f"⛔ Pre-Ticket Blocked: {pre_err}")
            return

        def done(res: Any) -> None:
            if res:
                params, warns = res
                self._validate_and_confirm(screen, params, warns, on_activity, on_done)

        screen.app.push_screen(OrderTicket(info, mode), done)

    def _validate_and_confirm(
        self,
        screen: Any,
        params: dict,
        warns: list[str],
        on_activity: Callable[[str], None] | None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Run pre-trade risk validation before opening the confirmation dialog."""
        positions = getattr(screen, "positions", [])
        funds_avail = 0.0
        try:
            if hasattr(screen, "funds") and screen.funds:
                funds_avail = float(screen.funds[0].get("tradingLimit") or screen.funds[0].get("cashBalance") or 0.0)
        except Exception:
            pass

        ref_price = 0.0
        try:
            feed_key = f"{params.get('exchange', 'NC')}{params.get('scripCode', '')}"
            if hasattr(screen.app, "raw_ticks") and feed_key in screen.app.raw_ticks:
                ref_price = float(screen.app.raw_ticks[feed_key].get("ltp") or 0.0)
        except Exception:
            pass

        risk_res = self.risk_engine.validate_order(
            order_params=params,
            positions=positions,
            quote_price=ref_price,
            available_funds=funds_avail,
        )

        # Hard risk violation -> Block execution
        if not risk_res.allowed:
            audit_trail.record(
                event_type="RISK_BLOCKED",
                symbol=params.get("tradingSymbol", ""),
                exchange=params.get("exchange", "NC"),
                side=params.get("transactionType", "B"),
                quantity=int(params.get("quantity") or 0),
                price=float(params.get("price") or 0.0),
                reason="; ".join(risk_res.violations),
                payload=params,
            )
            msg = f"⛔ ORDER BLOCKED BY RISK ENGINE:\n" + "\n".join(f"• {v}" for v in risk_res.violations)
            screen.app.notify(msg, severity="error", timeout=10)
            if on_activity:
                on_activity(f"⛔ Risk Blocked: {'; '.join(risk_res.violations)}")
            return

        # Combine warnings from builder and risk engine, prominently displaying risk score
        risk_score_str = f"Risk Score: {risk_res.risk_score}/100 [{risk_res.risk_rating}]"
        all_warns = [risk_score_str] + list(warns) + [f"Risk: {w}" for w in risk_res.warnings]
        if risk_res.estimated_margin > 0:
            all_warns.append(f"Est. Margin: ₹{risk_res.estimated_margin:,.2f}")

        # Record intent in order store & audit log
        self.order_store.record_intent(params)
        self._confirm(screen, params, all_warns, on_activity, on_done)

    def _confirm(
        self,
        screen: Any,
        params: dict,
        warns: list[str],
        on_activity: Callable[[str], None] | None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        from sktui.screens.modals import Confirm

        def on_ok() -> None:
            screen.run_worker(lambda: self._submit(screen, params, on_activity, on_done), thread=True)

        screen.app.push_screen(
            Confirm(f"Confirm {params['requestType']}", order_summary(params, warns), self._client.paper),
            lambda ok: on_ok() if ok else None,
        )

    def _submit(
        self,
        screen: Any,
        p: dict,
        on_activity: Callable[[str], None] | None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        side = "▲ BUY" if p.get("transactionType") == "B" else "▼ SELL"
        desc = f"{side} {p['quantity']} × {p['tradingSymbol']}"
        log  = on_activity or (lambda _: None)

        self.risk_engine.record_order_submission()

        try:
            r = self._client.submit(p)
            msg = f"✓ {p['requestType']} {desc} → {r}"
            log(msg)
            # Record submission in audit trail
            order_id = str(r.get("orderId") if isinstance(r, dict) else (p.get("orderId") or ""))
            audit_trail.record(
                event_type="ORDER_SUBMITTED",
                symbol=p.get("tradingSymbol", ""),
                exchange=p.get("exchange", "NC"),
                side=p.get("transactionType", "B"),
                quantity=int(p.get("quantity") or 0),
                price=float(p.get("price") or 0.0),
                order_id=order_id,
                status="SUBMITTED",
                payload={"request": p, "response": r},
            )
            screen.app.call_from_thread(screen.app.notify, f"✓ {p['requestType']} submitted: {str(r)[:120]}")
        except Exception as e:
            err_msg = str(e)
            hint = ""
            if "ip address is not allowed" in err_msg.lower():
                hint = " (Whitelist your public IP in Sharekhan API portal or run sktui --paper)"
            log(f"✗ {p['requestType']} {desc} FAILED: {e}{hint}")
            audit_trail.record(
                event_type="ORDER_SUBMIT_FAILED",
                symbol=p.get("tradingSymbol", ""),
                exchange=p.get("exchange", "NC"),
                side=p.get("transactionType", "B"),
                quantity=int(p.get("quantity") or 0),
                price=float(p.get("price") or 0.0),
                reason=err_msg,
                payload=p,
            )
            sev = "error"
            notice = "IP Blocked: Whitelist IP in Sharekhan API Portal or use --paper mode" if hint else f"Order failed: {e}"
            screen.app.call_from_thread(screen.app.notify, notice, severity=sev, timeout=12 if hint else 5)
        if on_done:
            on_done()

    def cancel(
        self,
        screen: Any,
        order_id: str,
        on_activity: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Cancel a single order by ID (runs in the calling thread)."""
        log = on_activity or (lambda _: None)
        try:
            r = self._client.cancel_by_id(order_id)
            log(f"✓ CANCEL {order_id}: {r}")
            audit_trail.record(
                event_type="ORDER_CANCEL_SUBMITTED",
                symbol="",
                order_id=order_id,
                status="CANCEL_SENT",
                payload={"response": r},
            )
        except Exception as e:
            log(f"✗ CANCEL {order_id} FAILED: {e}")
            audit_trail.record(
                event_type="ORDER_CANCEL_FAILED",
                symbol="",
                order_id=order_id,
                reason=str(e),
            )
            try:
                screen.app.call_from_thread(screen.app.notify, f"Cancel {order_id}: {e}", severity="error")
            except Exception:
                pass
        if on_done:
            on_done()

    def cancel_many(
        self,
        screen: Any,
        ids: list[str],
        on_activity: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """Cancel a list of order IDs (runs in the calling thread)."""
        for oid in ids:
            self.cancel(screen, oid, on_activity)
        if on_done:
            on_done()

    @staticmethod
    def build(f: dict, mode: str, customer_id: Any, login_id: str) -> tuple[dict, list[str]]:
        """Thin proxy to utils.build_order — keeps callers import-free."""
        return build_order(f, mode, customer_id, login_id)

    @staticmethod
    def row_to_info(r: dict) -> dict:
        """Convert a raw order record dict into OrderTicket info dict format."""
        from sktui.utils import norm_expiry
        t    = str(get(r, "buySell", "transactionType", default="B")).upper()[:1]
        prod = get(r, "productType", default="")
        opt  = str(get(r, "optionType", default="")).upper()
        return {
            "orderId":       get(r, "orderId"),
            "scripCode":     get(r, "scripCode",    default=None),
            "tradingSymbol": get(r, "tradingSymbol"),
            "exchange":      get(r, "exchange",      default="NC"),
            "side":          "S" if t == "S" else "B",
            "quantity":      get(r, "orderQty", "quantity", default=1),
            "executedQty":   get(r, "execQty",       default=0),
            "price":         get(r, "orderPrice", "price", default="0"),
            "triggerPrice":  get(r, "trigPrice", "triggerPrice", default="0"),
            "rmsCode":       get(r, "rmsCode",        default="ANY"),
            "afterHour":     get(r, "afterHour",      default="N"),
            "validity":      get(r, "goodTill",       default="GFD"),
            "productType":   prod,
            "instType":      get(r, "instrumentType", default=""),
            "optionType":    opt,
            "strike":        get(r, "strikePrice",    default=0),
            "expiry":        norm_expiry(get(r, "expiryDate", default="")),
        }
