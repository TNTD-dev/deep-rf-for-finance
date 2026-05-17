"""Lazy JSON file cache with mtime-based invalidation (PKG-11).

Per-app singleton stored on ``app.state.cache``. Each ``get(path)`` call:
- stat() the path (cheap, ~50µs)
- if mtime unchanged, return cached dict (no I/O)
- else read + parse + cache, return fresh dict
- missing file → return None (caller decides 404 vs default)
- malformed JSON → log WARNING + return None (same as missing — surface as 404)

NOT thread-safe; uvicorn runs async single-thread per worker and the demo
doesn't fork. NOT functools.lru_cache — that has no mtime-invalidation hook.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class JSONFileCache:
    def __init__(self) -> None:
        self._store: dict[Path, tuple[float, dict]] = {}

    def get(self, path: Path) -> dict | None:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            self._store.pop(path, None)
            return None
        cached = self._store.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("cache read failed for %s: %s", path, e)
            return None
        self._store[path] = (mtime, data)
        return data

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)
