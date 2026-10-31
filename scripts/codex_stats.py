"""Reproduce recorded work receipts and Git evidence without inferring agent usage."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ("accepted", "edited", "rejected")


@dataclass(frozen=True)
class Receipt:
    lane: str
    outcome: str
    task: str
    line: int


@dataclass(frozen=True)
class Commit:
    sha: str
    timestamp: str
    subject: str


def receipts(text: str) -> tuple[list[Receipt], list[int]]:
    """Count each explicit seven-column receipt once; disclose malformed rows."""
    found: list[Receipt] = []
    malformed: list[int] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if not cells or cells[0].casefold() == "time" or all(re.fullmatch(r"[:\s-]+", cell) for cell in cells):
            continue
        if len(cells) != 7 or not re.fullmatch(r"P[1-4](?:\s+auxiliary)?", cells[1]) or cells[4] not in OUTCOMES:
            malformed.append(number)
            continue
        found.append(Receipt(cells[1].split()[0], cells[4], cells[2], number))
    return found, malformed


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def commits(root: Path, paths: tuple[str, ...] = ()) -> list[Commit]:
    args = ["log", "--no-merges", "--min-parents=1", "--format=%H%x09%cI%x09%s", "HEAD"]
    if paths:
        args += ["--", *paths]
    output = git(root, *args)
    return [Commit(*line.split("\t", 2)) for line in output.splitlines() if line]


def plan_markers(text: str) -> tuple[int, int]:
    """Count explicit decisions and nonempty discovery paragraphs, not model calls."""
    decisions = len(re.findall(r"(?im)^\s*(?:[-*]\s*)?Decision(?:\s+[^:\n]{1,60})?:", text))
    discoveries = 0
    in_discoveries = False
    in_paragraph = False
    for line in text.splitlines():
        if line.startswith("#"):
            in_discoveries = "surprises" in line.casefold() or "discoveries" in line.casefold()
            in_paragraph = False
        elif in_discoveries:
            if not line.strip():
                in_paragraph = False
            elif not in_paragraph or re.match(r"^\s*[-*] ", line):
                discoveries += 1
                in_paragraph = True
    return decisions, discoveries


def render(root: Path) -> str:
    log = (root / "docs/tracking/CODEX_LOG.md").read_text(encoding="utf-8")
    rows, malformed = receipts(log)
    history = commits(root)
    lane_commits: Counter[str] = Counter()
    for commit in history:
        match = re.match(r"^S\d+ (P[1-4]):", commit.subject)
        if match:
            lane_commits[match[1]] += 1
    lines = ["# Recorded Codex build evidence", "", f"Git snapshot: `{git(root, 'rev-parse', 'HEAD')}`.", "",
             "This report counts recorded receipts, not unique tasks, people, sessions or productivity. "
             "A task can have multiple implementation/review/publication receipts. No test totals are summed across runs.", "",
             "| Lane | Logged receipts | Accepted | Edited | Rejected | S-prefix commits |",
             "|---|---:|---:|---:|---:|---:|"]
    for lane in ("P1", "P2", "P3", "P4"):
        counts = Counter(row.outcome for row in rows if row.lane == lane)
        lines.append(f"| {lane} | {sum(counts.values())} | {counts['accepted']} | {counts['edited']} | {counts['rejected']} | {lane_commits[lane]} |")
    lines += ["", f"Parsed {len(rows)} receipt rows. Malformed/unrecognized table rows: "
              + (", ".join(map(str, malformed)) if malformed else "none") + ".",
              "", "## Application history", "",
              "Non-merge, non-root commits touching backend/, frontend/ or scripts/. "
              "Prepared _outside-repo/ tooling and the repository initialization commit are excluded. "
              "Times are Git committer timestamps; they are not coding-duration measurements."]
    app_history = commits(root, ("backend", "frontend", "scripts"))
    lines.append(f"Application-path commits: {len(app_history)}.")
    runtime = sorted(commits(root, ("backend/app", "frontend/src", "scripts", ":(exclude)scripts/dev")),
                     key=lambda item: (datetime.fromisoformat(item.timestamp), item.sha))
    lines.append(f"Runtime/script commits: {len(runtime)}; excludes tests, phase-control files and scripts/dev setup.")
    if runtime:
        for label, commit in (("First runtime/script change", runtime[0]), ("Latest runtime/script change", runtime[-1])):
            lines.append(f"- {label}: {commit.timestamp}, `{commit.sha}`, {commit.subject}.")
    lines += ["", "## Plan evidence", "", "Explicit Decision markers and discovery paragraphs are text counts, not independently verified decisions or findings.",
              "", "| Plan | Decision markers | Discovery paragraphs/bullets |", "|---|---:|---:|"]
    for path in sorted((root / ".agent/plans").glob("P[1-4].md")):
        decision_count, discoveries = plan_markers(path.read_text(encoding="utf-8"))
        lines.append(f"| {path.name} | {decision_count} | {discoveries} |")
    lines += ["", "## Review and fix-loop receipts", "",
              "The following are matching log rows, not a count of distinct review findings or resolved bugs:"]
    for row in rows:
        if re.search(r"review|fix|loop|correct|repair", row.task, re.I):
            lines.append(f"- CODEX_LOG.md:{row.line} — {row.lane}, {row.outcome}: {row.task}.")
    lines += ["", "## Unavailable measurements", "",
              "- Exact chat/thread count: NOT VERIFIED; Git and Markdown do not enumerate sessions.",
              "- Exact skill invocation count: NOT VERIFIED; mentions and planned commands are not executions.",
              "- Distinct /review findings: NOT VERIFIED; use linked gate/review receipts and avoid deduplicating by guesswork.",
              "- Model/token/cost totals: not inferred from logs; use the run accounting reports.",
              "", "## Reproduction", "", "Run `python scripts/codex_stats.py` from this checkout. "
              "Inputs are HEAD history, docs/tracking/CODEX_LOG.md and .agent/plans/P1–P4.md at execution time. "
              "Working-tree document edits are included; rerun after integration for submission numbers.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    destination = args.output or args.root / "docs/results/codex-usage.md"
    report = render(args.root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report, encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
