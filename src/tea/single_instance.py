"""One running tea per user: QLockFile plus a local socket (ARCHITECTURE section 1).

The socket is a Unix domain socket in the runtime dir. It never touches the network.
"""

from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from tea.logging_setup import log_event

SOCKET_NAME = "tea-ipc"
LOCK_NAME = "tea.lock"
_MAX_MESSAGE = 64


class SingleInstance(QObject):
    """`acquire()` in the first process; later processes call `notify_running()` and exit."""

    message = Signal(str)

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self._folder = folder
        self._lock = QLockFile(str(folder / LOCK_NAME))
        self._lock.setStaleLockTime(0)  # stale only when the owning process is gone
        self._socket_path = str(folder / SOCKET_NAME)
        self._server: QLocalServer | None = None
        self._clients: list[QLocalSocket] = []

    def acquire(self) -> bool:
        self._folder.mkdir(parents=True, exist_ok=True)
        if not self._lock.tryLock(100):
            return False
        QLocalServer.removeServer(self._socket_path)
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._socket_path):
            log_event("ipc_listen_failed", error=server.serverError().name)
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def notify_running(self, message: str = "show", timeout_ms: int = 1000) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._socket_path)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(f"{message}\n".encode())
        socket.flush()
        # flush() often sends everything at once; then there is nothing left to wait for.
        ok = socket.bytesToWrite() == 0 or socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return ok

    def release(self) -> None:
        for socket in self._clients:
            socket.readyRead.disconnect()
            socket.disconnected.disconnect()
            socket.abort()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._lock.isLocked():
            self._lock.unlock()

    def _on_connection(self) -> None:
        assert self._server is not None
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._clients.append(socket)
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._drop(s))
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        while socket.canReadLine():
            raw = bytes(socket.readLine(_MAX_MESSAGE).data()).decode("utf-8", "replace").strip()
            if raw:
                self.message.emit(raw)

    def _drop(self, socket: QLocalSocket) -> None:
        self._read(socket)
        if socket in self._clients:
            self._clients.remove(socket)
        socket.deleteLater()
