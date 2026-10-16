"""アプリが覚えておく値（ウィジェットの位置など）。ユーザーが編集する設定ファイルとは分ける。"""

import json
import logging
from pathlib import Path
from typing import Any

from kotoba_desktop.config import app_dir

log = logging.getLogger(__name__)


class State:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_dir() / "state.json"
        self._data: dict[str, Any] = {}
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except OSError, ValueError:
            log.warning("state.json を読めないので初期値で始めます", exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("state.json を保存できません", exc_info=True)
