#!/usr/bin/env python3
"""Collect PostgreSQL commit-range metadata without reading diffs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"


def run_git(args: list[str], cwd: Path, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def verify_commit(repo: Path, commit: str) -> str:
    return run_git(["rev-parse", "--verify", f"{commit}^{{commit}}"], repo).strip()


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=str(repo),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def choose_range(repo: Path, first: str, second: str) -> tuple[str, str, str]:
    first_full = verify_commit(repo, first)
    second_full = verify_commit(repo, second)
    if is_ancestor(repo, first_full, second_full):
        return first_full, second_full, "first-to-second"
    if is_ancestor(repo, second_full, first_full):
        return second_full, first_full, "second-to-first"
    raise SystemExit(
        "The two commits are not on one ancestry path. Provide two commits from the same line of history."
    )


def parse_log(raw: str) -> list[dict[str, object]]:
    commits: list[dict[str, object]] = []
    for record in raw.strip(RECORD_SEP + "\n").split(RECORD_SEP):
        if not record.strip():
            continue
        parts = record.lstrip("\n").split(FIELD_SEP, 7)
        if len(parts) != 8:
            raise SystemExit("Unexpected git log format; cannot parse commit metadata.")
        full, short, author, author_email, date, parents, subject, body = parts
        commits.append(
            {
                "id": full.strip(),
                "short_id": short.strip(),
                "author": author.strip(),
                "author_email": author_email.strip(),
                "author_date": date.strip(),
                "parents": parents.strip().split() if parents.strip() else [],
                "is_merge": len(parents.strip().split()) > 1,
                "subject": subject.strip(),
                "body": body.strip(),
            }
        )
    return commits


def find_reverts(commits: list[dict[str, object]]) -> dict[str, object]:
    by_full = {str(c["id"]): c for c in commits}
    reverted_by: dict[str, list[str]] = {}
    reverting_commits: list[str] = []

    patterns = [
        re.compile(r'This reverts commit ([0-9a-f]{7,40})', re.IGNORECASE),
        re.compile(r"Revert \"(.+)\""),
    ]

    for commit in commits:
        text = f"{commit['subject']}\n{commit['body']}"
        matched = False
        for sha in patterns[0].findall(text):
            target = by_full.get(sha)
            if target is None:
                matches = [item for full, item in by_full.items() if full.startswith(sha)]
                target = matches[0] if len(matches) == 1 else None
            if target:
                reverted_by.setdefault(str(target["short_id"]), []).append(str(commit["short_id"]))
                matched = True
        if patterns[1].search(str(commit["subject"])):
            matched = True
        if matched:
            reverting_commits.append(str(commit["short_id"]))

    return {
        "reverted_by": reverted_by,
        "reverting_commits": sorted(set(reverting_commits)),
        "exclude_suggested": sorted(set(reverting_commits) | set(reverted_by.keys())),
    }


def collect(repo: Path, first: str, second: str) -> dict[str, object]:
    older, newer, direction = choose_range(repo, first, second)
    fmt = (
        f"%H{FIELD_SEP}%h{FIELD_SEP}%an{FIELD_SEP}%ae{FIELD_SEP}%ad"
        f"{FIELD_SEP}%P{FIELD_SEP}%s{FIELD_SEP}%B{RECORD_SEP}"
    )
    raw = run_git(
        ["log", "--reverse", "--date=short", f"--format={fmt}", f"{older}^..{newer}"],
        repo,
    )
    commits = parse_log(raw)
    short_older = run_git(["rev-parse", "--short", older], repo).strip()
    short_newer = run_git(["rev-parse", "--short", newer], repo).strip()
    return {
        "repository": str(repo),
        "input": {"first": first, "second": second},
        "range": {
            "older": older,
            "newer": newer,
            "older_short": short_older,
            "newer_short": short_newer,
            "direction": direction,
            "inclusive_spec": f"{short_older}^..{short_newer}",
        },
        "commit_count": len(commits),
        "reverts": find_reverts(commits),
        "commits": commits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect inclusive PostgreSQL commit metadata without diffs."
    )
    parser.add_argument("commitid1")
    parser.add_argument("commitid2")
    parser.add_argument("--output", "-o", help="Write JSON to this path.")
    args = parser.parse_args()

    repo = Path(run_git(["rev-parse", "--show-toplevel"], Path.cwd()).strip())
    required = ["src/backend", "src/include", "configure.ac"]
    missing = [item for item in required if not (repo / item).exists()]
    if missing:
        raise SystemExit(
            "This does not look like a PostgreSQL source checkout; missing: "
            + ", ".join(missing)
        )

    data = collect(repo, args.commitid1, args.commitid2)
    encoded = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = repo / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
        print(str(output))
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
