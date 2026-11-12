"""Execution trace replay and self-healing visualization utilities."""

from __future__ import annotations

import copy
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

from autocetacean.types import ExecutionContext, StepRecord


VALID_STATUSES = {"SUCCESS", "RETRY", "ROLLBACK", "HALT"}


class ReplayError(ValueError):
    """Raised when an execution trace cannot be decoded or validated."""


class ReplayEngine:
    """Load, inspect, and render a deterministic AutoCetacean execution trace.

    ``source`` may be a JSON/JSONL path, an :class:`ExecutionContext`, or an
    iterable of event dictionaries. Event dictionaries are copied on input so
    callers can safely reuse or mutate their original trace.
    """

    def __init__(self, source: Union[str, Path, ExecutionContext, Iterable[Mapping[str, Any]]]):
        self.events = self._load(source)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ReplayEngine":
        return cls(path)

    @classmethod
    def from_context(cls, context: ExecutionContext) -> "ReplayEngine":
        return cls(context)

    @classmethod
    def from_events(cls, events: Iterable[Mapping[str, Any]]) -> "ReplayEngine":
        return cls(events)

    @staticmethod
    def _load(source: Union[str, Path, ExecutionContext, Iterable[Mapping[str, Any]]]) -> list[dict[str, Any]]:
        if isinstance(source, ExecutionContext):
            raw = [ReplayEngine._record_to_event(i, record) for i, record in enumerate(source.trajectory, 1)]
        elif isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(str(path))
            if not path.is_file():
                raise ReplayError(f"trace path is not a file: {path}")
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ReplayError(f"unable to read trace: {exc}") from exc
            if not text.strip():
                raise ReplayError("trace file is empty")
            raw = ReplayEngine._decode_text(text, path)
        else:
            try:
                raw = list(source)
            except TypeError as exc:
                raise ReplayError("trace source must be a path, ExecutionContext, or event iterable") from exc
        events = []
        for index, item in enumerate(raw, 1):
            if not isinstance(item, Mapping):
                raise ReplayError(f"event {index} must be a JSON object")
            event = dict(item)
            event.setdefault("step_index", index)
            event.setdefault("timestamp", index)
            event.setdefault("node_name", "unknown")
            event.setdefault("state_before", {})
            event.setdefault("state_after", event.get("state_before", {}))
            event.setdefault("action", "execute")
            event.setdefault("error_message", event.get("error"))
            event.setdefault("checkpoint_id", None)
            status = str(event.get("status", "SUCCESS")).upper()
            if status not in VALID_STATUSES:
                raise ReplayError(f"event {index} has invalid status: {status!r}")
            event["status"] = status
            try:
                event["step_index"] = int(event["step_index"])
            except (TypeError, ValueError) as exc:
                raise ReplayError(f"event {index} has invalid step_index") from exc
            if not isinstance(event["node_name"], str):
                raise ReplayError(f"event {index} node_name must be a string")
            events.append(event)
        return events

    @staticmethod
    def _decode_text(text: str, path: Path) -> list[Any]:
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            items = []
            for line_no, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ReplayError(f"invalid JSON/JSONL at line {line_no}: {exc.msg}") from exc
            if not items:
                raise ReplayError(f"invalid JSON/JSONL trace: {path}")
            return items
        if isinstance(document, list):
            return document
        if isinstance(document, dict):
            for key in ("events", "trace", "records"):
                if key in document:
                    if not isinstance(document[key], list):
                        raise ReplayError(f"trace field {key!r} must be an array")
                    return document[key]
            return [document]
        raise ReplayError("JSON trace must be an object or array")

    @staticmethod
    def _record_to_event(index: int, record: StepRecord) -> dict[str, Any]:
        metadata = dict(record.metadata or {})
        state_before = metadata.pop("state_before", copy.deepcopy(record.input_data))
        state_after = metadata.pop("state_after", copy.deepcopy(record.output_data))
        if not isinstance(state_before, dict):
            state_before = {"input": state_before}
        if not isinstance(state_after, dict):
            state_after = {"output": state_after}
        return {
            "step_index": index,
            "timestamp": record.timestamp,
            "node_name": record.node_name,
            "state_before": state_before,
            "state_after": state_after,
            "action": metadata.pop("action", "execute"),
            "status": metadata.pop("status", "HALT" if record.error else "SUCCESS"),
            "error_message": record.error,
            "checkpoint_id": metadata.pop("checkpoint_id", None),
            "duration_ms": record.duration_ms,
            "metadata": metadata,
        }

    @property
    def records(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(event) for event in self.events]

    @staticmethod
    def _timestamp(value: Any) -> Optional[float]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
        return None

    @staticmethod
    def _diff(before: Any, after: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return {} if before == after else {"$": {"before": before, "after": after}}
        keys = sorted(set(before) | set(after))
        return {str(key): {"before": before.get(key), "after": after.get(key)} for key in keys if before.get(key) != after.get(key)}

    def render_terminal(self, format: str = "ansi") -> str:
        if format not in {"ansi", "plain"}:
            raise ValueError("format must be 'ansi' or 'plain'")
        ansi = format == "ansi"
        colors = {"SUCCESS": "\033[32m", "RETRY": "\033[33m", "ROLLBACK": "\033[35m", "HALT": "\033[31m"}
        lines = ["AutoCetacean Execution Replay", "=" * 31]
        for position, event in enumerate(self.events):
            status = event["status"]
            marker = {"SUCCESS": "✓", "RETRY": "↻", "ROLLBACK": "↩", "HALT": "✗"}[status]
            checkpoint = f"  checkpoint={event['checkpoint_id']}" if event.get("checkpoint_id") else ""
            error = f"  error={event['error_message']}" if event.get("error_message") else ""
            diff = self._diff(event.get("state_before", {}), event.get("state_after", {}))
            diff_text = f"  diff={','.join(diff)}" if diff else ""
            prefix = f"{colors[status]}{marker} [{event['step_index']:>3}] {event['node_name']}" if ansi else f"{marker} [{event['step_index']:>3}] {event['node_name']}"
            suffix = "\033[0m" if ansi else ""
            lines.append(f"{prefix} -- {event.get('action', 'execute')} [{status}]{checkpoint}{diff_text}{error}{suffix}")
            if position < len(self.events) - 1:
                lines.append("  │")
        if not self.events:
            lines.append("(no execution steps)")
        summary = self.export_summary()
        lines.extend(["", f"Steps: {summary['total_steps']}  Success: {summary['successful_steps']}  Rollbacks: {summary['rollback_count']}  Convergence: {summary['self_healing_convergence_rate']:.1%}"])
        return "\n".join(lines)

    def export_html(self, output_path: Union[str, Path]) -> None:
        summary = self.export_summary()
        cards = []
        for event in self.events:
            status = event["status"]
            diff = self._diff(event.get("state_before", {}), event.get("state_after", {}))
            diff_json = html.escape(json.dumps(diff, ensure_ascii=False, indent=2))
            cards.append(f'''<article class="step {status.lower()}"><header><span class="badge">{html.escape(status)}</span><strong>#{event["step_index"]} {html.escape(str(event["node_name"]))}</strong><time>{html.escape(str(event.get("timestamp", "")))}</time></header><p>{html.escape(str(event.get("action", "execute")))}{(" · " + html.escape(str(event["error_message"]))) if event.get("error_message") else ""}{(" · checkpoint " + html.escape(str(event["checkpoint_id"]))) if event.get("checkpoint_id") else ""}</p><details><summary>State diff ({len(diff)} fields)</summary><pre>{diff_json}</pre></details></article>''')
        document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoCetacean Execution Replay</title><style>:root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#10131a;color:#e8edf5}}body{{max-width:1000px;margin:0 auto;padding:32px}}h1{{margin-bottom:4px}}.summary{{color:#a9b5c7;margin-bottom:28px}}.timeline{{border-left:2px solid #344054;padding-left:20px}}.step{{background:#171d28;border:1px solid #2b3546;border-left:5px solid #697586;border-radius:10px;margin:0 0 16px;padding:16px;box-shadow:0 4px 15px #0003}}.success{{border-left-color:#36c275}}.retry{{border-left-color:#e4ad36}}.rollback{{border-left-color:#b982ed}}.halt{{border-left-color:#f06464}}header{{display:flex;gap:12px;align-items:center}}header time{{margin-left:auto;color:#8d9aae;font-size:.85em}}.badge{{font-size:.75em;font-weight:700;padding:3px 8px;border-radius:99px;background:#344054}}.success .badge{{background:#1d6941}}.retry .badge{{background:#80601b}}.rollback .badge{{background:#59367c}}.halt .badge{{background:#873737}}pre{{white-space:pre-wrap;background:#0b0e13;padding:12px;border-radius:6px;overflow:auto}}summary{{cursor:pointer;color:#a9b5c7}}</style></head><body><h1>AutoCetacean Execution Replay</h1><div class="summary">{summary["total_steps"]} steps · {summary["successful_steps"]} successful · {summary["rollback_count"]} rollbacks · {summary["self_healing_convergence_rate"]:.1%} self-healing convergence</div><main class="timeline">{"".join(cards) or "<p>No execution steps.</p>"}</main></body></html>'''
        Path(output_path).write_text(document, encoding="utf-8")

    def export_summary(self) -> dict[str, Any]:
        timestamps = [self._timestamp(e.get("timestamp")) for e in self.events]
        valid_times = [t for t in timestamps if t is not None]
        durations = sum(float(e.get("duration_ms", 0) or 0) for e in self.events)
        elapsed_ms = max(0.0, (max(valid_times) - min(valid_times)) * 1000) if len(valid_times) >= 2 else durations
        successes = sum(e["status"] == "SUCCESS" for e in self.events)
        retries = sum(e["status"] == "RETRY" for e in self.events)
        rollbacks = sum(e["status"] == "ROLLBACK" for e in self.events)
        halts = sum(e["status"] == "HALT" for e in self.events)
        incidents = retries + rollbacks + halts
        recovered = 0
        for i, event in enumerate(self.events):
            if event["status"] in {"RETRY", "ROLLBACK"} and any(later["status"] == "SUCCESS" and later["node_name"] == event["node_name"] for later in self.events[i + 1:]):
                recovered += 1
        convergence = recovered / (retries + rollbacks) if retries + rollbacks else (1.0 if self.events and not halts else 0.0)
        return {"total_steps": len(self.events), "successful_steps": successes, "retry_count": retries, "rollback_count": rollbacks, "halt_count": halts, "duration_ms": round(elapsed_ms, 3), "duration_seconds": round(elapsed_ms / 1000, 3), "self_healing_convergence_rate": round(convergence, 6), "incident_count": incidents}


__all__ = ["ReplayEngine", "ReplayError"]
