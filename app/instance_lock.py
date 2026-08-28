from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


INSTANCE_ALREADY_RUNNING_EXIT_CODE = 73


class InstanceAlreadyRunningError(RuntimeError):
    """Второй экземпляр LapBase обнаружен до подключения к БД и миграций."""


class InstanceLock:
    """Кроссплатформенная блокировка процесса на локальном файле проекта."""

    def __init__(self, path: Path, version: str) -> None:
        self.path = path
        self.version = version
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")

        try:
            if os.name == "nt":
                self._acquire_windows(handle)
            else:
                self._acquire_posix(handle)
        except Exception:
            handle.close()
            raise

        self._handle = handle
        self._write_metadata()

    @staticmethod
    def _acquire_posix(handle: BinaryIO) -> None:
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstanceAlreadyRunningError("LapBase уже запущен") from exc

    @staticmethod
    def _acquire_windows(handle: BinaryIO) -> None:
        import msvcrt

        # msvcrt.locking требует хотя бы один байт в блокируемом диапазоне.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b" ")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise InstanceAlreadyRunningError("LapBase уже запущен") from exc

    def _write_metadata(self) -> None:
        if self._handle is None:
            return
        payload = f"pid={os.getpid()}\nversion={self.version}\n".encode("utf-8")
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(payload)
        self._handle.flush()

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return

        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    # Закрытие дескриптора всё равно освободит lock.
                    pass
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> InstanceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
