import json
import pickle
import time
from pathlib import Path


class PersistentCache:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parent.parent / ".quantara" / "persistent_cache")
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, key):
        return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(key))[:180]

    def path(self, namespace, key, suffix):
        directory = self.root / self._safe_name(namespace)
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{self._safe_name(key)}.{suffix}"

    def get_pickle(self, namespace, key, ttl_seconds=None, default=None):
        path = self.path(namespace, key, "pkl")
        if not path.exists():
            return default
        if ttl_seconds is not None and time.time() - path.stat().st_mtime > ttl_seconds:
            return default
        try:
            with path.open("rb") as handle:
                return pickle.load(handle)
        except Exception:
            return default

    def set_pickle(self, namespace, key, value):
        path = self.path(namespace, key, "pkl")
        with path.open("wb") as handle:
            pickle.dump(value, handle)

    def get_json(self, namespace, key, ttl_seconds=None, default=None):
        path = self.path(namespace, key, "json")
        if not path.exists():
            return default
        if ttl_seconds is not None and time.time() - path.stat().st_mtime > ttl_seconds:
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def set_json(self, namespace, key, value):
        path = self.path(namespace, key, "json")
        path.write_text(json.dumps(value, default=str), encoding="utf-8")


cache = PersistentCache()

