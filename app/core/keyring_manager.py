import json
import os
import stat

SERVICE_NAME = "extractor-for-excel"

try:
    import keyring as _kr
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False


class KeyManager:
    def __init__(self, project_dir: str = ""):
        self.project_dir = project_dir
        self._keyring_ok = self._check_keyring()

    @staticmethod
    def _check_keyring() -> bool:
        if not HAS_KEYRING:
            return False
        try:
            _kr.get_password(SERVICE_NAME, "_probe")
            return True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._keyring_ok or bool(self.project_dir)

    def get(self, name: str) -> str | None:
        if self._keyring_ok:
            try:
                val = _kr.get_password(SERVICE_NAME, name)
                if val is not None:
                    return val
            except Exception:
                pass
        return self._read_fallback(name)

    def set(self, name: str, value: str):
        if self._keyring_ok:
            try:
                _kr.set_password(SERVICE_NAME, name, value)
                return
            except Exception:
                pass
        if self.project_dir:
            self._write_fallback(name, value)

    def delete(self, name: str):
        if self._keyring_ok:
            try:
                _kr.delete_password(SERVICE_NAME, name)
                return
            except Exception:
                pass
        if self.project_dir:
            self._remove_fallback(name)

    def _fb_path(self) -> str:
        return os.path.join(self.project_dir, "project.keys.json") if self.project_dir else ""

    def _read_fallback(self, name: str) -> str | None:
        path = self._fb_path()
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f).get(name)
        except Exception:
            return None

    def _write_fallback(self, name: str, value: str):
        path = self._fb_path()
        if not path:
            return
        data = {}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        data[name] = value
        with open(path, "w") as f:
            json.dump(data, f)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    def _remove_fallback(self, name: str):
        path = self._fb_path()
        if not path or not os.path.exists(path):
            return
        with open(path) as f:
            data = json.load(f)
        data.pop(name, None)
        if data:
            with open(path, "w") as f:
                json.dump(data, f)
        else:
            os.remove(path)
