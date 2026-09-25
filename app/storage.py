import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path, default: Any):
        self.path = path
        self.default = default
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.write(default)

    def read(self) -> Any:
        with self.lock:
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except (json.JSONDecodeError, FileNotFoundError):
                return deepcopy(self.default)

    def write(self, value: Any) -> None:
        with self.lock:
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(self.path)

    def update(self, mutator):
        with self.lock:
            value = self.read()
            result = mutator(value)
            self.write(value)
            return result

