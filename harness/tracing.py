"""Structured JSONL tracing for reproducible runs without logging raw prompts."""

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Protocol

from .run_state import RunState


def to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_primitive(item) for item in value]
    return value


class TraceSink(Protocol):
    def record(self, event: str, state: RunState, **details: object) -> None:
        ...


class NullTraceSink:
    def record(self, event: str, state: RunState, **details: object) -> None:
        del event, state, details


class JsonlTraceSink:
    def __init__(self, path: Path):
        self.path = path

    def record(self, event: str, state: RunState, **details: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record: Dict[str, Any] = {
            "event": event,
            "run_id": state.run_id,
            "phase": state.phase,
            "retrieval_rounds_used": state.retrieval_rounds_used,
            "remaining_round_budget": state.remaining_round_budget,
            "remaining_request_budget": state.remaining_request_budget,
            "no_progress_rounds": state.no_progress_rounds,
            "details": details,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(to_primitive(record), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
