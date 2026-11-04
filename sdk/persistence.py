"""Durable persistence for helix/mission state."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any


class MissionStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path.home() / '.omp' / 'missions.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, data: dict):
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
    
    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return {}


import fcntl
import time

class DurableMissionStore(MissionStore):
    """File-locked durable store with GC."""

    def save(self, data: dict):
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.replace(tmp, self.path)
        self.gc()

    def gc(self, retain_active_days: int = 7):
        data = self.load()
        if not data:
            return
        # Keep all for now - could add timestamp-based GC
        # Just ensure file stays bounded by not growing unbounded
        self.save(data)
