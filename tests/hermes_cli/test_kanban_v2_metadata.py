"""Phase 3 tests for new-card v2 metadata enrichment."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    """Isolated HERMES_HOME with an empty kanban DB."""
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _task(conn, task_id: str) -> kb.Task:
    task = kb.get_task(conn, task_id)
    assert task is not None
    return task


def test_new_card_with_canonical_assignee_writes_v2_metadata(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Coordinate rollout", assignee="orchestrator")
        task = _task(conn, tid)

    assert task.assignee == "orchestrator"
    assert task.legacy_assignee is None
    assert task.canonical_assignee == "orchestrator"
    assert task.lane == "ops-control"
    assert task.resolution_type == "canonical_passthrough"
    assert task.needs_review is False


def test_new_card_with_exact_alias_preserves_legacy_and_canonical(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Research market", assignee="researcher-opus")
        task = _task(conn, tid)

    assert task.assignee == "researcher"
    assert task.legacy_assignee == "researcher-opus"
    assert task.canonical_assignee == "researcher"
    assert task.resolution_type == "exact_alias"
    assert task.needs_review is False


def test_researcher_opus_writes_opus_max_reasoning_metadata(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Deep research brief", assignee="researcher-opus")
        task = _task(conn, tid)

    assert task.mode == "deep"
    assert task.provider_hint == "opus"
    assert task.model_class == "opus"
    assert task.reasoning_effort_schema == "anthropic_opus"
    assert task.reasoning_effort == "max"


def test_codex_eng_writes_openai_high_and_codex_executor_metadata(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Implement small API fix", assignee="codex-eng")
        task = _task(conn, tid)

    assert task.assignee == "engineer"
    assert task.legacy_assignee == "codex-eng"
    assert task.canonical_assignee == "engineer"
    assert task.executor_hint == "codex-cli"
    assert task.provider_hint == "openai"
    assert task.model_class == "gpt-5.5"
    assert task.reasoning_effort_schema == "openai_gpt55"
    assert task.reasoning_effort == "high"
    assert task.resolution_type == "exact_alias"
    assert task.needs_review is False


def test_complex_risky_codex_engineering_context_gets_extra_high_reasoning(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(
            conn,
            title="Debug risky auth session migration",
            body="Complex production authentication/session failure; risky cross-cutting refactor.",
            assignee="codex-eng",
        )
        task = _task(conn, tid)

    assert task.canonical_assignee == "engineer"
    assert task.reasoning_effort_schema == "openai_gpt55"
    assert task.reasoning_effort == "extra-high"


def test_content_strategist_strategy_context_maps_to_analyst(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(
            conn,
            title="Content architecture and positioning strategy",
            body="Map framing, audience design, and content architecture before drafting.",
            assignee="content-strategist",
        )
        task = _task(conn, tid)

    assert task.assignee == "analyst"
    assert task.legacy_assignee == "content-strategist"
    assert task.canonical_assignee == "analyst"
    assert task.mode == "content-architecture"
    assert task.tags == ["brand", "content-strategy"]
    assert task.provider_hint == "opus"
    assert task.reasoning_effort_schema == "anthropic_opus"
    assert task.reasoning_effort == "max"
    assert task.resolution_type == "contextual_inference"
    assert task.needs_review is False


def test_content_strategist_ambiguous_context_needs_review_without_fake_route(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Content plan", assignee="content-strategist")
        task = _task(conn, tid)

    assert task.assignee == "content-strategist"
    assert task.legacy_assignee == "content-strategist"
    assert task.canonical_assignee is None
    assert task.resolution_type == "ambiguous"
    assert task.confidence < 0.6
    assert task.needs_review is True
    assert "content-strategist" in task.resolver_reason


def test_unknown_assignee_needs_review_without_fake_route(kanban_home):
    with kb.connect() as conn:
        tid = kb.create_task(conn, title="Mystery task", assignee="unknown-agent")
        task = _task(conn, tid)

    assert task.assignee == "unknown-agent"
    assert task.legacy_assignee == "unknown-agent"
    assert task.canonical_assignee is None
    assert task.resolution_type == "unmappable"
    assert task.confidence == 0.0
    assert task.needs_review is True
    assert "No canonical agent or alias" in task.resolver_reason


def test_new_v2_metadata_columns_are_added_to_legacy_boards(tmp_path):
    db_path = tmp_path / "legacy-kanban.db"
    conn = kb.sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT,
            assignee TEXT,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at INTEGER NOT NULL,
            started_at INTEGER,
            completed_at INTEGER,
            workspace_kind TEXT NOT NULL DEFAULT 'scratch',
            workspace_path TEXT,
            claim_lock TEXT,
            claim_expires INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    with kb.connect(db_path) as migrated:
        cols = {row["name"] for row in migrated.execute("PRAGMA table_info(tasks)")}

    for col in kb.V2_METADATA_COLUMNS:
        assert col in cols
