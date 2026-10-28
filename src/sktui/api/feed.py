"""Websocket feed logic for live quotes and ack subscriptions."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from .auth import ApiError

WS_URL = "wss://stream.sharekhan.com/skstream/api/stream"


class Feed:
    """Streams quotes ("full" mode) and order acknowledgements."""

    def __init__(self, access_token: str, api_key: str, customer_id,
                 keys: Callable[[], list[str]], on_message: Callable[[dict], None],
                 on_status: Callable[[str, bool], None]):
        self.access_token, self.api_key, self.customer_id = access_token, api_key, customer_id
        self.keys, self.on_message, self.on_status = keys, on_message, on_status
        self.ws = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws_lock = threading.Lock()
        self.ready = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            with self._ws_lock:
                if self.ws:
                    self.ws.close()
        except Exception:
            pass

    def send(self, obj: dict) -> None:
        if not self.ws or not self.ready:
            return
        payload = json.dumps(obj, separators=(",", ":"))
        try:
            with self._ws_lock:
                if self.ws and self.ready:
                    self.ws.send(payload)
        except Exception:
            pass

    def subscribe(self, key: str, mode: str = "full") -> None:
        if not key:
            return
        self.send({"action": "feed", "key": [mode], "value": [key]})

    def unsubscribe(self, key: str) -> None:
        if not key:
            return
        self.send({"action": "unsubscribe", "key": ["feed"], "value": [key]})

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
                on_close=lambda w, c, m: self._on_close(w, c, m),
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

    def _on_close(self, ws, code, msg) -> None:
        self.ready = False
        self.ws = None
        self.on_status("Feed: disconnected", False)

    def _on_msg(self, ws, raw) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        kind = msg.get("message") if isinstance(msg, dict) else None
        try:
            if kind == "connect":
                self.ready = True
                ws.send(json.dumps({"action": "subscribe", "key": ["feed", "ack"], "value": [""]}, separators=(",", ":")))
                self.on_status("Feed: connected", False)
            elif kind == "subscribe":
                ws.send(json.dumps({"action": "ack", "key": [""], "value": [self.customer_id]}, separators=(",", ":")))
                for k in self.keys():
                    ws.send(json.dumps({"action": "feed", "key": ["full"], "value": [k]}, separators=(",", ":")))
                self.on_status("Feed: subscribed", False)
        except Exception as e:
            self.on_status(f"Feed send failed: {e}", True)
        self.on_message(msg)
