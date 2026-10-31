"""Offline evidence accounting using unrelated histories and explicit receipts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import codex_stats as stats


def test_receipt_parser_preserves_escaped_pipes_and_reports_invalid_rows() -> None:
    text = """| time | lane | task | files | accepted/edited/rejected | human change | test |
|---|---|---|---|---|---|---|
| 11:00 | P2 auxiliary | inspect a \\| b | x.py | edited | request | 2 pass |
| 11:01 | P3 | invalid | x.py | invented | none | none |
| 11:02 | P1 | missing | accepted |
"""
    rows, invalid = stats.receipts(text)
    assert rows == [stats.Receipt("P2", "edited", "inspect a | b", 3)]
    assert invalid == [4, 5]


def test_plan_markers_count_explicit_evidence_not_headings_or_skill_mentions() -> None:
    assert stats.plan_markers("""### Decision Log
- Decision: use the narrow input
Run $self-review later.
### Surprises & Discoveries
First paragraph
continues here.

- Second finding
- Third finding
### Outcomes
Nothing further
""") == (1, 3)


def test_report_excludes_prepared_and_root_history_and_does_not_infer_sessions(tmp_path: Path) -> None:
    stats.git(tmp_path, "init")
    stats.git(tmp_path, "config", "user.name", "Test Author")
    stats.git(tmp_path, "config", "user.email", "test@example.invalid")
    for name in ("docs/tracking", ".agent/plans", "backend", "_outside-repo"):
        (tmp_path / name).mkdir(parents=True)
    log = tmp_path / "docs/tracking/CODEX_LOG.md"
    log.write_text("| 12:00 | P3 | review adapter | x | accepted | none | 1 pass |\n", encoding="utf-8")
    (tmp_path / "backend/prepared.py").write_text("# root material\n", encoding="utf-8")
    stats.git(tmp_path, "add", ".")
    stats.git(tmp_path, "commit", "-m", "Preparation init")
    (tmp_path / "backend/new.py").write_text("# built today\n", encoding="utf-8")
    stats.git(tmp_path, "add", ".")
    stats.git(tmp_path, "commit", "-m", "S8 P3: unrelated adapter")
    (tmp_path / "_outside-repo/tool.py").write_text("# prepared tool\n", encoding="utf-8")
    stats.git(tmp_path, "add", ".")
    stats.git(tmp_path, "commit", "-m", "Tooling note")
    report = stats.render(tmp_path)
    assert "Application-path commits: 1." in report
    assert "| P3 | 1 | 1 | 0 | 0 | 1 |" in report
    assert "Exact chat/thread count: NOT VERIFIED" in report
    assert "Exact skill invocation count: NOT VERIFIED" in report
    assert "Preparation init" not in report
    assert "Tooling note" not in report
    assert stats.main(["--root", str(tmp_path)]) == 0
    assert (tmp_path / "docs/results/codex-usage.md").read_text(encoding="utf-8") == report


def test_runtime_history_excludes_setup_and_phase_control(tmp_path: Path) -> None:
    stats.git(tmp_path, "init")
    stats.git(tmp_path, "config", "user.name", "Variant Author")
    stats.git(tmp_path, "config", "user.email", "variant@example.invalid")
    (tmp_path / "README.md").write_text("preparation", encoding="utf-8")
    stats.git(tmp_path, "add", ".")
    stats.git(tmp_path, "commit", "-m", "init")
    for name, message in (("scripts/dev/setup.py", "setup only"),
                          ("backend/app/variant.py", "S9 P1: runtime"),
                          ("backend/tests/PHASE", "phase control")):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture", encoding="utf-8")
        stats.git(tmp_path, "add", ".")
        stats.git(tmp_path, "commit", "-m", message)
    history = stats.commits(tmp_path, ("backend/app", "frontend/src", "scripts", ":(exclude)scripts/dev"))
    assert [commit.subject for commit in history] == ["S9 P1: runtime"]
