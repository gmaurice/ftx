import json, time, logging
from threading import Thread, Lock

from websocket import WebSocketApp
import traceback

class WebsocketManager:
    _CONNECT_TIMEOUT_S = 5

    def __init__(self):
        self.connect_lock = Lock()
        self.ws = None

    def _get_url(self):
        raise NotImplementedError()

    def _on_message(self, ws, message):
        raise NotImplementedError()

    def send(self, message):
        self.connect()
        self.ws.send(message)

    def send_json(self, message):
        self.send(json.dumps(message))

    def _connect(self):
        assert not self.ws, "ws should be closed before attempting to connect"
        logging.info('Connecting to ' + self._get_url() + '...')
        self.ws = WebSocketApp(
            self._get_url(),
            on_message=self._wrap_callback(self._on_message),
            on_close=self._wrap_callback(self._on_close),
            on_error=self._wrap_callback(self._on_error),
            on_pong=self._on_pong,
        )
        wst = Thread(target=self._run_websocket, args=(self.ws,))
        wst.daemon = True
        wst.start()

        # Wait for socket to connect
        ts = time.time()
        while self.ws and (not self.ws.sock or not self.ws.sock.connected):
            if time.time() - ts > self._CONNECT_TIMEOUT_S:
                self.ws = None
                return
            time.sleep(0.1)

        # ws_ping = Thread(target=self._heartbeat)
        # ws_ping.daemon = True
        # ws_ping.start()

    def _wrap_callback(self, f):
        def wrapped_f(ws, *args, **kwargs):
            if ws is self.ws:
                try:
                    f(ws, *args, **kwargs)
                except Exception as e:
                    traceback.print_exc()
                    raise Exception(f'Error running websocket callback: {e}')
        return wrapped_f

    def _run_websocket(self, ws):
        try:
            ws.run_forever(ping_interval=15, ping_payload='{"op":"ping"}')
        except Exception as e:
            raise Exception(f'Unexpected error while running websocket: {e}')
        finally:
            self._reconnect(ws)

    def _reconnect(self, ws):
        assert ws is not None, '_reconnect should only be called with an existing ws'
        if ws is self.ws:
            self.ws = None
            ws.close()
            self.connect()

    def connect(self):
        if self.ws:
            return
        with self.connect_lock:
            while not self.ws:
                self._connect()
                if self.ws:
                    return

    def _on_pong(self, ws, message):
        return

    def _on_close(self, ws):
        logging.warn('Closed connection, reconnecting...')
        self._reconnect(ws)

    def _on_error(self, ws, error):
        logging.error(str(error))
        self._reconnect(ws)

    def reconnect(self) -> None:
        if self.ws is not None:
            self._reconnect(self.ws)
