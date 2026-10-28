#!/usr/bin/env python3
"""Score a pilot result project against a fixture's seeded defects.

    python .pilot/score.py <result project dir> [--json out.json] [--fixture server-audit]

The result project is never modified: it is copied to a temporary directory,
and every test run happens in that copy. Three suites run there:

- project suite: `node --test` exactly as the result project defines it;
- visible suite: the fixture's original test/ files, against the result's src/;
- hidden suite: one hidden test file per hidden-test defect, run separately,
  so each exit code scores one defect.

Static defects are scored by deterministic regular-expression checks over the
result's src/ files (see defects.json). Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

PILOT = Path(__file__).resolve().parent
SOURCE_SUFFIXES = {".js", ".cjs", ".mjs"}
COPY_IGNORE = (".git", "node_modules", ".claude", ".agents", ".codex", ".alchemy", "__pycache__")
SUITE_TIMEOUT = 300
HIDDEN_TIMEOUT = 120
CATEGORIES = ("correctness", "security", "dead-code", "architecture", "duplication")


def kill_tree(process: subprocess.Popen) -> None:
    """Kill a process and every child it started; node --test forks per file."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def run(command: list[str], cwd: Path, timeout: int) -> dict:
    """Run a command with a hard timeout. Returns exit code (None on timeout) and output."""
    environment = {key: value for key, value in os.environ.items() if key != "NODE_OPTIONS"}
    environment["NO_COLOR"] = "1"
    process = subprocess.Popen(
        command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **group_kwargs(),
    )
    try:
        out, err = process.communicate(timeout=timeout)
        code, timed_out = process.returncode, False
    except subprocess.TimeoutExpired:
        kill_tree(process)
        out, err = process.communicate()
        code, timed_out = None, True
    return {
        "exit": code,
        "timed_out": timed_out,
        "stdout": out.decode("utf-8", errors="replace"),
        "stderr": err.decode("utf-8", errors="replace"),
    }


def tap_counts(output: str) -> dict:
    """Read the summary lines node's TAP reporter prints (# pass N, # fail N)."""
    counts = {}
    for key in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        match = re.search(rf"^# {key} (\d+)\s*$", output, re.M)
        counts[key] = int(match.group(1)) if match else None
    return counts


def failing_tests(output: str) -> list[str]:
    return re.findall(r"^\s*not ok \d+ - (.+)$", output, re.M)[:20]


def node_suite(files: list[str], cwd: Path, timeout: int) -> dict:
    """Run node's test runner on explicit files, or on its defaults when files is empty."""
    outcome = run(["node", "--test", "--test-reporter=tap", *files], cwd, timeout)
    counts = tap_counts(outcome["stdout"])
    passed = (
        outcome["exit"] == 0
        and not outcome["timed_out"]
        and (counts["fail"] or 0) == 0
        and (counts["pass"] or 0) > 0
    )
    return {
        "pass": passed,
        "exit": outcome["exit"],
        "timed_out": outcome["timed_out"],
        "counts": counts,
        "failing": failing_tests(outcome["stdout"]),
    }


def source_files(root: Path) -> dict[str, str]:
    """Every JavaScript source under src/, keyed by project-relative POSIX path."""
    src = root / "src"
    if not src.is_dir():
        return {}
    files = {}
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_SUFFIXES and "node_modules" not in path.parts:
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8", errors="replace")
    return files


def static_check(check: dict, files: dict[str, str]) -> tuple[bool, str]:
    """Apply one deterministic check from defects.json. Returns (holds, evidence)."""
    kind = check["kind"]
    if kind == "absent":
        hits = [path for path, text in files.items() if re.search(check["pattern"], text)]
        return not hits, f"matches in {hits}" if hits else f"no match in {len(files)} source files"
    if kind == "present":
        hits = [path for path, text in files.items() if re.search(check["pattern"], text)]
        return bool(hits), f"matches in {hits}" if hits else f"no match in {len(files)} source files"
    if kind == "absent_in_paths":
        scope = [path for path in files if re.search(check["path_pattern"], path)]
        hits = [path for path in scope if re.search(check["pattern"], files[path])]
        if hits:
            return False, f"matches in {hits}"
        return True, f"no match in {len(scope)} files whose path matches {check['path_pattern']!r}"
    if kind == "co_occurrence":
        scope = [path for path, text in files.items() if re.search(check["when"], text)]
        missing = [path for path in scope if not re.search(check["require"], files[path])]
        if not scope:
            return False, f"no source file matches {check['when']!r}"
        if missing:
            return False, f"{missing} match {check['when']!r} without {check['require']!r}"
        return True, f"all of {scope} also match {check['require']!r}"
    raise ValueError(f"unknown static check kind: {kind}")


def tree_fingerprint(root: Path) -> str:
    """Path, size, and mtime of every file outside .git: proof the run left the result untouched."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        stat = path.stat()
        digest.update(f"{path.relative_to(root).as_posix()}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()


def load_defects(fixture: str) -> tuple[Path, dict]:
    directory = PILOT / fixture
    defects = json.loads((directory / "defects.json").read_text(encoding="utf-8"))
    return directory, defects


def score(result_dir: Path, fixture: str = "server-audit") -> dict:
    """Score result_dir without modifying it. Returns the score record."""
    result_dir = Path(result_dir).resolve()
    if not result_dir.is_dir():
        raise FileNotFoundError(f"result project not found: {result_dir}")
    fixture_dir, ground_truth = load_defects(fixture)
    before = tree_fingerprint(result_dir)
    node_version = run(["node", "--version"], result_dir, 30)["stdout"].strip()

    scratch = Path(tempfile.mkdtemp(prefix="alchemy-pilot-score-")).resolve()
    try:
        copy = scratch / "project"
        shutil.copytree(result_dir, copy, ignore=shutil.ignore_patterns(*COPY_IGNORE))

        project_suite = node_suite([], copy, SUITE_TIMEOUT)

        visible_dir = copy / ".pilot-visible"
        shutil.copytree(fixture_dir / "project" / "test", visible_dir)
        visible_files = sorted(f".pilot-visible/{path.name}" for path in visible_dir.glob("*.test.js"))
        visible_suite = node_suite(visible_files, copy, SUITE_TIMEOUT)

        hidden_dir = copy / ".pilot-hidden"
        shutil.copytree(fixture_dir / "hidden-tests", hidden_dir)

        files = source_files(copy)
        scored = []
        for defect in ground_truth["defects"]:
            method = defect["scoring"]["method"]
            if method == "hidden-test":
                outcome = node_suite([f".pilot-hidden/{defect['scoring']['test']}"], copy, HIDDEN_TIMEOUT)
                fixed = outcome["pass"]
                evidence = (
                    f"{defect['scoring']['test']}: exit {outcome['exit']}"
                    + (", timed out" if outcome["timed_out"] else "")
                    + (f", failing {outcome['failing']}" if outcome["failing"] else "")
                )
            elif method == "static":
                fixed, evidence = static_check(defect["scoring"]["check"], files)
            else:
                raise ValueError(f"{defect['id']}: unknown scoring method {method}")
            scored.append({
                "id": defect["id"],
                "category": defect["category"],
                "file": defect["file"],
                "method": method,
                "fixed": fixed,
                "evidence": evidence,
            })
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    by_category = {category: {"fixed": 0, "total": 0} for category in CATEGORIES}
    for item in scored:
        by_category[item["category"]]["total"] += 1
        by_category[item["category"]]["fixed"] += int(item["fixed"])
    return {
        "schema": "alchemy-pilot-score/1",
        "fixture": fixture,
        "node": node_version,
        "visible_tests_pass": visible_suite["pass"],
        "visible_tests": visible_suite,
        "project_tests_pass": project_suite["pass"],
        "project_tests": project_suite,
        "defects": scored,
        "by_category": by_category,
        "defects_fixed": sum(int(item["fixed"]) for item in scored),
        "defects_total": len(scored),
        "result_unmodified": tree_fingerprint(result_dir) == before,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a pilot result project against the seeded defects.")
    parser.add_argument("result", type=Path, help="result project directory (never modified)")
    parser.add_argument("--json", type=Path, help="also write the score record to this file")
    parser.add_argument("--fixture", default="server-audit", help="fixture directory under .pilot/ (default: server-audit)")
    args = parser.parse_args()
    if shutil.which("node") is None:
        print("ERROR: node is not on PATH", file=sys.stderr)
        return 2
    try:
        record = score(args.result, args.fixture)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    text = json.dumps(record, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
