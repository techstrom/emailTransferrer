"""Persistent state management for processed message identifiers."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterable, Set


class StateStore:
    """Simple JSON-based store tracking processed message identifiers."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"sources": {}})

    def _read(self) -> dict:
        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, data: dict) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        tmp_path.replace(self._path)

    def get_processed_uids(self, source_name: str) -> Set[str]:
        with self._lock:
            data = self._read()
            return set(data.get("sources", {}).get(source_name, []))

    def record_processed_uids(self, source_name: str, uids: Iterable[str]) -> None:
        uids_set = set(uids)
        if not uids_set:
            return

        with self._lock:
            data = self._read()
            sources = data.setdefault("sources", {})
            existing = set(sources.get(source_name, []))
            updated = sorted(existing.union(uids_set))
            sources[source_name] = updated
            self._write(data)

    def clear_source(self, source_name: str) -> None:
        with self._lock:
            data = self._read()
            sources = data.get("sources", {})
            if source_name in sources:
                del sources[source_name]
                self._write(data)

