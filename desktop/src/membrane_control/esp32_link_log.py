"""Small persistent log of ESP32 commands and connection failures."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from uuid import uuid4


class _LinkLogHandler(RotatingFileHandler):
    def handleError(self, record):
        # A full disk or locked file must not interrupt a valve command.
        pass


class Esp32LinkLog:
    def __init__(self, path, *, max_bytes=256 * 1024, backups=3):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backups = backups
        self._instance = uuid4().hex[:12]
        self._handler = None
        self._closed = False

    def record(self, event, **fields):
        if self._closed:
            return
        try:
            entry = {
                "time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "app_instance": self._instance,
                "event": event,
                **fields,
            }
            line = json.dumps(entry, allow_nan=False, separators=(",", ":"))
            if len(line) + len(os.linesep) >= self.max_bytes:
                return
            if self._handler is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._handler = _LinkLogHandler(self.path, maxBytes=self.max_bytes,
                    backupCount=self.backups, encoding="utf-8", delay=True)
            self._handler.handle(logging.LogRecord("esp32_link", logging.INFO,
                "", 0, line, (), None))
        except (OSError, TypeError, ValueError):
            pass

    def recent_text(self, max_bytes=24 * 1024):
        """Read whole recent lines, oldest first, within one combined limit."""
        remaining = max_bytes
        chunks = []
        for index in range(self.backups + 1):
            if remaining <= 0:
                break
            path = self.path if index == 0 else self.path.with_name(f"{self.path.name}.{index}")
            try:
                with path.open("rb") as source:
                    size = source.seek(0, os.SEEK_END)
                    start = max(0, size - remaining)
                    source.seek(start)
                    chunk = source.read(remaining)
            except OSError:
                continue
            remaining -= len(chunk)
            if start:
                chunk = chunk.partition(b"\n")[2]
            if chunk and not chunk.endswith(b"\n"):
                before, separator, _ = chunk.rpartition(b"\n")
                chunk = before + separator
            chunks.append(chunk)
        return b"".join(reversed(chunks)).decode("utf-8", errors="replace")

    def close(self):
        self._closed = True
        handler, self._handler = self._handler, None
        if handler is not None:
            try:
                handler.close()
            except OSError:
                pass
