"""Local run artifacts, replay comparison metadata, and preference exports."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from openra_env.cli import docker_manager as docker

BASE_DIR = Path.home() / ".openra-rl"
RUNS_DIR = BASE_DIR / "runs"
PREFERENCES_DIR = BASE_DIR / "preferences"
EXPORTS_DIR = BASE_DIR / "arena-exports"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_slug() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    slug = slug.strip("-")
    return slug or "run"


def _json_dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _redact_sensitive(data: Any) -> Any:
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            key_lower = key.lower()
            if key_lower in {"api_key", "hf_token", "authorization"}:
                redacted[key] = "***"
            else:
                redacted[key] = _redact_sensitive(value)
        return redacted
    if isinstance(data, list):
        return [_redact_sensitive(item) for item in data]
    return data


def sanitize_config_snapshot(config: Any) -> dict[str, Any]:
    """Return a JSON-safe, secret-redacted config snapshot."""
    if hasattr(config, "model_dump"):
        raw = config.model_dump()
    elif isinstance(config, dict):
        raw = deepcopy(config)
    else:
        raw = deepcopy(vars(config))
    return _redact_sensitive(raw)


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{_timestamp_slug()}"


def save_run_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Persist a structured run artifact under ~/.openra-rl/runs/."""
    run_id = artifact.get("run_id") or new_run_id()
    path = RUNS_DIR / f"{run_id}.json"
    saved = dict(artifact)
    saved["run_id"] = run_id
    saved["saved_at"] = _utc_iso()
    saved["path"] = str(path)
    _json_dump(path, saved)
    return saved


def load_run_artifact(path_or_run_id: str | Path) -> dict[str, Any]:
    """Load a run artifact by path or run_id."""
    path = Path(path_or_run_id)
    if path.exists():
        return _json_load(path)

    candidate = RUNS_DIR / f"{path_or_run_id}.json"
    if candidate.exists():
        return _json_load(candidate)

    raise FileNotFoundError(f"Run artifact not found: {path_or_run_id}")


def list_run_artifacts() -> list[Path]:
    """Return run artifact paths sorted newest first."""
    if not RUNS_DIR.exists():
        return []
    return sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _resolve_local_replay(filename: str) -> Optional[Path]:
    if not filename:
        return None
    candidate = docker.LOCAL_REPLAY_DIR / filename
    if candidate.exists():
        return candidate
    return None


def _replay_filename_from_path(replay_path: str) -> str:
    if not replay_path:
        return ""
    return Path(replay_path).name


def resolve_compare_entry(reference: Optional[str], slot: str) -> dict[str, Any]:
    """Resolve a compare input into run/replay metadata.

    Supported inputs:
    - run_id
    - path to run artifact JSON
    - path to .orarep replay
    - replay filename in ~/.openra-rl/replays/
    - None: newest run artifacts are chosen elsewhere
    """
    if not reference:
        raise FileNotFoundError("Missing compare reference")

    path = Path(reference)
    if path.exists() and path.suffix.lower() == ".json":
        artifact = load_run_artifact(path)
        return build_compare_entry_from_artifact(artifact, slot=slot)

    try:
        artifact = load_run_artifact(reference)
        return build_compare_entry_from_artifact(artifact, slot=slot)
    except FileNotFoundError:
        pass

    if path.exists() and path.suffix.lower() == ".orarep":
        replay_path = str(path.resolve())
        return {
            "slot": slot,
            "run_id": _slugify(path.stem),
            "run_path": "",
            "label": path.stem,
            "title": path.stem,
            "replay_path": replay_path,
            "replay_filename": path.name,
            "metadata": {
                "source": "replay",
                "map": "",
                "opponent": "",
                "model": "",
                "result": "",
                "ticks": "",
            },
        }

    local_replay = _resolve_local_replay(reference)
    if local_replay is not None:
        return {
            "slot": slot,
            "run_id": _slugify(local_replay.stem),
            "run_path": "",
            "label": local_replay.stem,
            "title": local_replay.stem,
            "replay_path": str(local_replay),
            "replay_filename": local_replay.name,
            "metadata": {
                "source": "replay",
                "map": "",
                "opponent": "",
                "model": "",
                "result": "",
                "ticks": "",
            },
        }

    raise FileNotFoundError(f"Could not resolve run or replay: {reference}")


def build_compare_entry_from_artifact(artifact: dict[str, Any], slot: str) -> dict[str, Any]:
    """Convert a run artifact into UI-friendly compare metadata."""
    replay = artifact.get("replay", {})
    replay_filename = replay.get("filename") or _replay_filename_from_path(replay.get("path", ""))
    local_replay = replay.get("local_path") or ""
    if not local_replay:
        candidate = _resolve_local_replay(replay_filename)
        local_replay = str(candidate) if candidate else replay.get("path", "")

    summary = artifact.get("summary", {})
    match = artifact.get("match", {})
    agent = artifact.get("agent", {})
    run_id = artifact.get("run_id") or _slugify(replay_filename or "run")
    label = agent.get("name") or agent.get("model") or run_id
    return {
        "slot": slot,
        "run_id": run_id,
        "run_path": artifact.get("path", str(RUNS_DIR / f"{run_id}.json")),
        "label": label,
        "title": f"{label} ({run_id})",
        "replay_path": local_replay,
        "replay_filename": replay_filename,
        "metadata": {
            "source": "run",
            "map": match.get("map_name", ""),
            "opponent": match.get("opponent", ""),
            "model": agent.get("model", ""),
            "result": summary.get("result", ""),
            "ticks": summary.get("ticks", ""),
        },
    }


def latest_compare_entries() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the newest two run artifacts as compare entries."""
    artifacts = list_run_artifacts()
    if len(artifacts) < 2:
        raise FileNotFoundError("Need at least two saved runs in ~/.openra-rl/runs/")
    left = build_compare_entry_from_artifact(_json_load(artifacts[0]), slot="left")
    right = build_compare_entry_from_artifact(_json_load(artifacts[1]), slot="right")
    return left, right


def comparison_record(
    left: dict[str, Any],
    right: dict[str, Any],
    preferred_side: str,
    label: str = "preferred",
) -> dict[str, Any]:
    """Build a saved preference JSON payload."""
    preferred_run_id = ""
    if preferred_side == "left":
        preferred_run_id = left.get("run_id", "")
    elif preferred_side == "right":
        preferred_run_id = right.get("run_id", "")

    comparison_id = f"cmp_{_timestamp_slug()}"
    return {
        "comparison_id": comparison_id,
        "created_at": _utc_iso(),
        "label": label,
        "preferred_side": preferred_side,
        "preferred_run_id": preferred_run_id,
        "left_run_id": left.get("run_id", ""),
        "right_run_id": right.get("run_id", ""),
        "left_run_path": left.get("run_path", ""),
        "right_run_path": right.get("run_path", ""),
        "left_replay_path": left.get("replay_path", ""),
        "right_replay_path": right.get("replay_path", ""),
        "left_metadata": left.get("metadata", {}),
        "right_metadata": right.get("metadata", {}),
    }


def save_preference(record: dict[str, Any]) -> Path:
    """Persist one preference JSON record."""
    comparison_id = record.get("comparison_id") or f"cmp_{_timestamp_slug()}"
    path = PREFERENCES_DIR / f"{comparison_id}.json"
    payload = dict(record)
    payload["comparison_id"] = comparison_id
    _json_dump(path, payload)
    return path


def list_preferences() -> list[Path]:
    """Return saved preference files sorted newest first."""
    if not PREFERENCES_DIR.exists():
        return []
    return sorted(PREFERENCES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _flatten_messages(messages: list[dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "?")
        if role == "tool":
            content = msg.get("content", "")
            lines.append(f"[tool:{msg.get('tool_call_id', '')}] {content}")
            continue
        text = msg.get("content", "")
        if text:
            lines.append(f"[{role}] {text}")
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                lines.append(f"[assistant_tool] {fn.get('name', '')} {fn.get('arguments', '{}')}")
    return "\n".join(lines)


def export_preference_pairs(output_path: Optional[str] = None) -> tuple[Path, int]:
    """Export preference pairs as JSONL for downstream training use."""
    records = []
    for pref_path in list_preferences():
        pref = _json_load(pref_path)
        preferred_side = pref.get("preferred_side")
        if preferred_side not in {"left", "right"}:
            continue

        chosen_path = pref.get(f"{preferred_side}_run_path", "")
        rejected_side = "right" if preferred_side == "left" else "left"
        rejected_path = pref.get(f"{rejected_side}_run_path", "")
        if not chosen_path or not rejected_path:
            continue

        try:
            chosen = load_run_artifact(chosen_path)
            rejected = load_run_artifact(rejected_path)
        except FileNotFoundError:
            continue

        chosen_messages = chosen.get("messages", [])
        rejected_messages = rejected.get("messages", [])
        records.append({
            "comparison_id": pref.get("comparison_id", ""),
            "created_at": pref.get("created_at", ""),
            "chosen_run_id": chosen.get("run_id", ""),
            "rejected_run_id": rejected.get("run_id", ""),
            "chosen": {
                "messages": chosen_messages,
                "text": _flatten_messages(chosen_messages),
                "summary": chosen.get("summary", {}),
                "match": chosen.get("match", {}),
                "agent": chosen.get("agent", {}),
                "replay": chosen.get("replay", {}),
            },
            "rejected": {
                "messages": rejected_messages,
                "text": _flatten_messages(rejected_messages),
                "summary": rejected.get("summary", {}),
                "match": rejected.get("match", {}),
                "agent": rejected.get("agent", {}),
                "replay": rejected.get("replay", {}),
            },
        })

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path:
        out = Path(output_path).expanduser()
    else:
        out = EXPORTS_DIR / f"preferences-{_timestamp_slug()}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return out, len(records)
