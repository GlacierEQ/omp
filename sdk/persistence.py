"""Durable persistence for helix/mission state."""

from __future__ import annotations
import json
import os
import fcntl
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


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


class DurableMissionStore(MissionStore):
    """File-locked durable store."""

    def save(self, data: dict):
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            json.dump(data, f, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        os.replace(tmp, self.path)


class GlobalStateStore:
    """Central durable state for all omp subsystems."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path.home() / '.omp' / 'global_state.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: Any):
        state = self.load_all()
        state[key] = data
        state['_meta'] = {'updated': datetime.now(timezone.utc).isoformat()}
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            json.dump(state, f, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        os.replace(tmp, self.path)

    def load_all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return {}

    def load(self, key: str, default=None):
        return self.load_all().get(key, default)
