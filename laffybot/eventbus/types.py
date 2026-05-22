from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GlobalEvent:
    type: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        data_str = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.type}\ndata: {data_str}\n\n"
