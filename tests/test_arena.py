"""Tests for local replay comparison and preference export helpers."""

import json
from pathlib import Path


def test_save_and_load_run_artifact(tmp_path, monkeypatch):
    from openra_env import arena_data

    monkeypatch.setattr(arena_data, "RUNS_DIR", tmp_path / "runs")
    saved = arena_data.save_run_artifact({
        "run_id": "run_test",
        "messages": [{"role": "system", "content": "hello"}],
    })
    loaded = arena_data.load_run_artifact("run_test")

    assert saved["run_id"] == "run_test"
    assert Path(saved["path"]).exists()
    assert loaded["messages"][0]["content"] == "hello"


def test_resolve_compare_entry_from_run_artifact(tmp_path, monkeypatch):
    from openra_env import arena_data

    runs_dir = tmp_path / "runs"
    replay_dir = tmp_path / "replays"
    monkeypatch.setattr(arena_data, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(arena_data.docker, "LOCAL_REPLAY_DIR", replay_dir)
    replay_dir.mkdir(parents=True)
    (replay_dir / "demo.orarep").write_text("stub", encoding="utf-8")

    arena_data.save_run_artifact({
        "run_id": "run_demo",
        "agent": {"name": "DemoBot", "model": "qwen3:4b"},
        "match": {"map_name": "singles", "opponent": "normal"},
        "summary": {"result": "win", "ticks": 1234},
        "replay": {"filename": "demo.orarep"},
        "messages": [],
    })

    entry = arena_data.resolve_compare_entry("run_demo", slot="left")
    assert entry["run_id"] == "run_demo"
    assert entry["replay_path"].endswith("demo.orarep")
    assert entry["metadata"]["map"] == "singles"


def test_export_preference_pairs(tmp_path, monkeypatch):
    from openra_env import arena_data

    runs_dir = tmp_path / "runs"
    prefs_dir = tmp_path / "preferences"
    export_dir = tmp_path / "exports"
    monkeypatch.setattr(arena_data, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(arena_data, "PREFERENCES_DIR", prefs_dir)
    monkeypatch.setattr(arena_data, "EXPORTS_DIR", export_dir)

    left = arena_data.save_run_artifact({
        "run_id": "run_left",
        "agent": {"model": "model-a"},
        "match": {"map_name": "singles"},
        "summary": {"result": "win"},
        "replay": {"filename": "left.orarep"},
        "messages": [{"role": "user", "content": "left"}],
    })
    right = arena_data.save_run_artifact({
        "run_id": "run_right",
        "agent": {"model": "model-b"},
        "match": {"map_name": "singles"},
        "summary": {"result": "lose"},
        "replay": {"filename": "right.orarep"},
        "messages": [{"role": "user", "content": "right"}],
    })

    pref = arena_data.comparison_record(
        {
            "run_id": left["run_id"],
            "run_path": left["path"],
            "replay_path": "left.orarep",
            "metadata": {},
        },
        {
            "run_id": right["run_id"],
            "run_path": right["path"],
            "replay_path": "right.orarep",
            "metadata": {},
        },
        preferred_side="left",
    )
    arena_data.save_preference(pref)

    export_path, count = arena_data.export_preference_pairs()
    lines = export_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])

    assert count == 1
    assert payload["chosen_run_id"] == "run_left"
    assert payload["rejected_run_id"] == "run_right"
    assert payload["chosen"]["text"].startswith("[user] left")
