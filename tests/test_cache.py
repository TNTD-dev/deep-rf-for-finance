"""Tests for backend/cache.py JSONFileCache."""

from __future__ import annotations

import json
import os
from pathlib import Path

from backend.cache import JSONFileCache


def test_cache_returns_none_for_missing_file(tmp_path: Path) -> None:
    cache = JSONFileCache()
    assert cache.get(tmp_path / "nope.json") is None
    assert cache.size() == 0


def test_cache_round_trips_dict(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": 1, "b": [2, 3]}))
    cache = JSONFileCache()
    out = cache.get(p)
    assert out == {"a": 1, "b": [2, 3]}
    assert cache.size() == 1
    # Second call hits cache (same dict identity since no reload).
    out2 = cache.get(p)
    assert out2 is out


def test_cache_invalidates_on_mtime_change(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"v": 1}))
    cache = JSONFileCache()
    assert cache.get(p) == {"v": 1}

    # Rewrite with a future mtime so the change is detectable.
    p.write_text(json.dumps({"v": 2}))
    future = p.stat().st_mtime + 10
    os.utime(p, (future, future))

    assert cache.get(p) == {"v": 2}
    assert cache.size() == 1


def test_cache_returns_none_for_malformed_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json at all")
    cache = JSONFileCache()
    assert cache.get(p) is None
    assert cache.size() == 0
