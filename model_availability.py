"""Model availability solidification - persistent health tracking."""

from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone


class ModelAvailability:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path.home() / '.omp' / 'model_health.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self):
        if not self.path.exists():
            return {'models': {}, 'updated': None}
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return {'models': {}, 'updated': None}

    def save(self):
        self._state['updated'] = datetime.now(timezone.utc).isoformat()
        tmp = self.path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(self._state, f, indent=2)
        os.replace(tmp, self.path)

    def mark_available(self, model_id: str, latency_ms: float = None):
        self._state['models'][model_id] = {
            'status': 'available',
            'last_success': datetime.now(timezone.utc).isoformat(),
            'latency_ms': latency_ms
        }
        self.save()

    def mark_unavailable(self, model_id: str, error: str = None):
        self._state['models'][model_id] = {
            'status': 'unavailable',
            'last_failure': datetime.now(timezone.utc).isoformat(),
            'error': error
        }
        self.save()

    def is_available(self, model_id: str) -> bool:
        m = self._state['models'].get(model_id)
        if not m:
            return True  # unverified allowed
        return m.get('status') != 'unavailable'

    def get_health(self):
        return self._state
