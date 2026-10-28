"""Sharekhan WebSocket feed client.

Protocol (per docs):
  connect -> server says message=="connect" -> send subscribe {feed, ack}
  -> on message=="subscribe" send the ack request and one feed request
     per scrip key such as "NC2885".
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

WS_URL = "wss://stream.sharekhan.com/skstream/api/stream"


class Feed:
    """Streams live quotes ("full" mode) and order acknowledgements.

    Parameters
    ----------
    access_token:  JWT session token.
    api_key:       Sharekhan API key.
    customer_id:   Numeric or string customer ID — sent in the ack frame.
    keys:          Callable that returns the current list of feed keys
                   (e.g. ["NC2885", "NF60530"]).  Called on each reconnect.
    on_message:    Callback fired for every parsed WebSocket message dict.
    on_status:     Callback fired for human-readable status strings;
                   second arg is ``True`` when the event is an error.
    """

    def __init__(
        self,
        access_token: str,
        api_key: str,
        customer_id: object,
        keys: Callable[[], list[str]],
        on_message: Callable[[dict], None],
        on_status: Callable[[str, bool], None],
    ):
        self.access_token  = access_token
        self.api_key       = api_key
        self.customer_id   = customer_id
        self.keys          = keys
        self.on_message    = on_message
        self.on_status     = on_status
        self.ws            = None
        self._stop         = threading.Event()
        self._thread: threading.Thread | None = None
        self.ready         = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    # ── Send helpers ──────────────────────────────────────────────────────────
    def send(self, obj: dict) -> None:
        if self.ws and self.ready:
            self.ws.send(json.dumps(obj))

    def subscribe(self, key: str, mode: str = "full") -> None:
        self.send({"action": "feed", "key": [mode], "value": [key]})

    def unsubscribe(self, key: str) -> None:
        self.send({"action": "unsubscribe", "key": ["feed"], "value": [key]})

    # ── Internal ──────────────────────────────────────────────────────────────
    def _run(self) -> None:
        import websocket  # websocket-client

        backoff = 2
        url = f"{WS_URL}?ACCESS_TOKEN={self.access_token}&API_KEY={self.api_key}"
        while not self._stop.is_set():
            self.ready = False
            self.ws = websocket.WebSocketApp(
                url,
                on_open=lambda w: self.on_status("Feed: socket open", False),
                on_message=self._on_msg,
                on_error=lambda w, e: self.on_status(f"Feed error: {e}", True),
                on_close=lambda w, c, m: self.on_status("Feed: disconnected", False),
            )
            started = time.time()
            try:
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.on_status(f"Feed crashed: {e}", True)
            if self._stop.is_set():
                break
            if time.time() - started > 30:
                backoff = 2
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 30)

    def _on_msg(self, ws, raw) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        kind = msg.get("message") if isinstance(msg, dict) else None
        try:
            if kind == "connect":
                self.ready = True
                ws.send(
                    json.dumps({"action": "subscribe", "key": ["feed", "ack"], "value": [""]})
                )
                self.on_status("Feed: connected", False)
            elif kind == "subscribe":
                ws.send(json.dumps({"action": "ack", "key": [""], "value": [self.customer_id]}))
                for k in self.keys():
                    ws.send(json.dumps({"action": "feed", "key": ["full"], "value": [k]}))
                self.on_status("Feed: subscribed", False)
        except Exception as e:
            self.on_status(f"Feed send failed: {e}", True)
        self.on_message(msg)
