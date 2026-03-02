"""
Deribit WebSocket client.

Runs an asyncio event loop in a dedicated daemon thread.
Pushes received data into a TickerDataStore for consumption
by the synchronous polling and Flask threads.
"""

import asyncio
import json
import logging
import threading

import websockets

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30
RECONNECT_BASE_DELAY = 1
RECONNECT_MAX_DELAY = 30


class DeribitWSClient:
    """Manages a single WebSocket connection to Deribit with auto-reconnect."""

    def __init__(self, store, url="wss://www.deribit.com/ws/api/v2"):
        self._store = store
        self._url = url
        self._loop = None
        self._thread = None
        self._ws = None
        self._subscribed_channels = set()
        self._pending_subscribes = set()
        self._pending_unsubscribes = set()
        self._channel_lock = threading.Lock()
        self._msg_id = 0
        self._connected = threading.Event()
        self._running = False

    def start(self):
        """Start the WebSocket thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the WebSocket thread to stop."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def subscribe(self, channels):
        """Thread-safe: request subscription to channels.

        Can be called from any thread. Takes effect on next send cycle
        or immediately if connected.
        """
        channels = set(channels)
        with self._channel_lock:
            new_channels = channels - self._subscribed_channels
            if not new_channels:
                return
            self._pending_subscribes.update(new_channels)
        if self._loop and self._connected.is_set():
            self._loop.call_soon_threadsafe(self._schedule_pending)

    def unsubscribe(self, channels):
        """Thread-safe: request unsubscription from channels."""
        channels = set(channels)
        with self._channel_lock:
            to_unsub = channels & self._subscribed_channels
            if not to_unsub:
                return
            self._pending_unsubscribes.update(to_unsub)
            self._pending_subscribes -= channels
        if self._loop and self._connected.is_set():
            self._loop.call_soon_threadsafe(self._schedule_pending)

    def is_connected(self):
        """Check if currently connected."""
        return self._connected.is_set()

    # ---- Internal ----

    def _schedule_pending(self):
        """Schedule _process_pending as an asyncio task (called via call_soon_threadsafe)."""
        asyncio.ensure_future(self._process_pending(), loop=self._loop)

    def _run_loop(self):
        """Entry point for the dedicated asyncio thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        """Outer loop: connect, run, reconnect on failure."""
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=None,
                    max_size=2**22,
                ) as ws:
                    self._ws = ws
                    delay = RECONNECT_BASE_DELAY
                    logger.info("WebSocket connected to %s", self._url)
                    await self._on_connected()
                    await self._receive_loop()
            except Exception:
                self._connected.clear()
                if self._running:
                    logger.exception("WebSocket connection lost")

            if not self._running:
                break
            logger.info("Reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _on_connected(self):
        """Set up heartbeat and resubscribe to all channels."""
        await self._send_rpc("public/set_heartbeat", {"interval": HEARTBEAT_INTERVAL})

        with self._channel_lock:
            self._pending_subscribes.update(self._subscribed_channels)
            self._subscribed_channels.clear()

        await self._process_pending()
        self._connected.set()

    async def _receive_loop(self):
        """Process incoming messages until disconnect."""
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            method = msg.get("method")

            # Heartbeat test_request — respond immediately
            if method == "heartbeat":
                if msg.get("params", {}).get("type") == "test_request":
                    await self._send_rpc("public/test", {})
                continue

            # Subscription notification
            if method == "subscription":
                self._handle_notification(msg.get("params", {}))
                continue

    def _handle_notification(self, params):
        """Route a subscription notification to the appropriate store update."""
        channel = params.get("channel", "")
        data = params.get("data")
        if not data:
            return

        if channel.startswith("deribit_price_index."):
            self._store.update_spot(
                index_name=data.get("index_name"),
                price=data.get("price"),
                timestamp=data.get("timestamp"),
            )
        elif channel.startswith("ticker."):
            greeks = data.get("greeks") or {}
            self._store.update_ticker(
                instrument_name=data.get("instrument_name", ""),
                delta=greeks.get("delta"),
                mark_iv=data.get("mark_iv"),
                timestamp=data.get("timestamp"),
            )

    async def _process_pending(self):
        """Send pending subscribe/unsubscribe requests."""
        with self._channel_lock:
            to_sub = list(self._pending_subscribes)
            to_unsub = list(self._pending_unsubscribes)
            self._pending_subscribes.clear()
            self._pending_unsubscribes.clear()

        if to_unsub:
            await self._send_rpc("public/unsubscribe", {"channels": to_unsub})
            with self._channel_lock:
                self._subscribed_channels -= set(to_unsub)
            logger.info("Unsubscribed from %d channels", len(to_unsub))
            stale = [ch.split(".")[1] for ch in to_unsub if ch.startswith("ticker.")]
            self._store.clear_tickers(stale)

        if to_sub:
            await self._send_rpc("public/subscribe", {"channels": to_sub})
            with self._channel_lock:
                self._subscribed_channels.update(to_sub)
            logger.info("Subscribed to %d channels (total: %d)",
                        len(to_sub), len(self._subscribed_channels))

    async def _send_rpc(self, method, params):
        """Send a JSON-RPC request."""
        self._msg_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params,
        }
        await self._ws.send(json.dumps(msg))
