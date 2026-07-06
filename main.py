from app import app, socketio
import os
import signal
import socket
import time


def _pids_on_port(port: int) -> list[int]:
    """Возвращает список PID, слушающих TCP-порт, через /proc/net/tcp (без внешних утилит)."""
    pids: list[int] = []
    hex_port = f"{port:04X}"
    own_pid = os.getpid()

    # Сначала ищем inode в /proc/net/tcp и /proc/net/tcp6
    inodes: set[str] = set()
    for tcp_file in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(tcp_file) as f:
                for line in f:
                    parts = line.split()
                    # local_address поле: XXXXXXXX:PORT, state 0A = LISTEN
                    if len(parts) < 10:
                        continue
                    local = parts[1]
                    state = parts[3]
                    inode = parts[9]
                    if local.endswith(f":{hex_port}") and state == "0A":
                        inodes.add(inode)
        except OSError:
            pass

    if not inodes:
        return pids

    # Затем сопоставляем inode → PID через /proc/<pid>/fd/
    try:
        for pid_str in os.listdir("/proc"):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            if pid == own_pid:
                continue  # не убиваем себя
            fd_dir = f"/proc/{pid}/fd"
            try:
                for fd in os.listdir(fd_dir):
                    try:
                        link = os.readlink(f"{fd_dir}/{fd}")
                        # socket:[inode]
                        if link.startswith("socket:["):
                            inode = link[8:-1]
                            if inode in inodes:
                                pids.append(pid)
                                break
                    except OSError:
                        pass
            except OSError:
                pass
    except OSError:
        pass

    return pids


def _free_port(port: int) -> None:
    """Завершает процессы, удерживающие порт. Использует только /proc — без fuser."""
    pids = _pids_on_port(port)
    for pid in pids:
        try:
            print(f"[startup] Освобождаем порт {port}: завершаем PID {pid}")
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    if pids:
        time.sleep(0.5)  # даём время на завершение


def _start_server(port: int, retries: int = 3) -> None:
    """Запускает Flask-SocketIO с повторными попытками при EADDRINUSE."""
    for attempt in range(retries):
        try:
            socketio.run(
                app,
                host="0.0.0.0",
                port=port,
                debug=False,
                allow_unsafe_werkzeug=True,
            )
            return
        except OSError as exc:
            import errno
            if exc.errno != errno.EADDRINUSE or attempt == retries - 1:
                raise
            print(f"[startup] Порт {port} занят (попытка {attempt + 1}/{retries}), освобождаем...")
            _free_port(port)
            time.sleep(1)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    _free_port(port)
    _start_server(port)
