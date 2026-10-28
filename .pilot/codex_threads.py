"""Recover the Codex agent tree of one pilot run from Codex's saved sessions.

`codex exec --json` does not always stream sub-agent activity, but Codex saves
every thread it runs, including spawned sub-agents, as a rollout under
`~/.codex/sessions/`. A sub-agent's first record names its parent thread and
its spawn depth, which is the runtime's own record that delegation happened.

Usage:
    python .pilot/codex_threads.py <result.json> [--sessions DIR] [--write]

Reads the run project's path from nothing the agent wrote: it matches
rollouts by the `cwd` Codex recorded and by the run's start and finish time.
With --write, the summary is stored in the result JSON under
`acceptance.codex_threads`; paths and the account name are redacted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_RE = re.compile(r"skills[/\\]+([a-z0-9-]+)[/\\]+SKILL\.md")
RUN_PROJECT_RE = re.compile(r"alchemy-pilot-[a-z]+-codex-[A-Za-z0-9_]+")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def rollout_threads(sessions: Path, start: datetime, finish: datetime) -> list[dict]:
    threads = []
    for path in sorted(sessions.rglob("rollout-*.jsonl")):
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if modified < start:
            continue
        lines = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        if not lines:
            continue
        meta = lines[0].get("payload", {})
        stamp = lines[0].get("timestamp") or meta.get("timestamp")
        if stamp and not (start <= parse_time(stamp) <= finish):
            continue
        threads.append({"meta": meta, "lines": lines})
    return threads


def summarize(thread: dict) -> dict:
    meta = thread["meta"]
    source = meta.get("source")
    spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    skills, messages, tool_calls = set(), [], 0
    for record in thread["lines"]:
        payload = record.get("payload", {})
        text = json.dumps(payload)
        skills.update(SKILL_RE.findall(text))
        if payload.get("type") in ("function_call", "custom_tool_call"):
            tool_calls += 1
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            for part in payload.get("content") or []:
                if isinstance(part, dict) and part.get("text"):
                    messages.append(part["text"][:600])
    return {
        "thread_id": meta.get("id"),
        "thread_source": meta.get("thread_source"),
        "parent_thread_id": spawn.get("parent_thread_id") or meta.get("parent_thread_id"),
        "depth": spawn.get("depth"),
        "agent_path": spawn.get("agent_path"),
        "agent_role": spawn.get("agent_role"),
        "skills_read": sorted(skills),
        "tool_calls": tool_calls,
        "assistant_messages": messages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result")
    parser.add_argument("--sessions", default=str(Path.home() / ".codex" / "sessions"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result_path = Path(args.result)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    start, finish = parse_time(result["started_at"]), parse_time(result["finished_at"])
    threads = [
        thread for thread in rollout_threads(Path(args.sessions), start, finish)
        if RUN_PROJECT_RE.search(str(thread["meta"].get("cwd", "")))
    ]
    summary = [summarize(thread) for thread in threads]
    roots = {item["thread_id"] for item in summary if item["thread_source"] != "subagent"}
    facts = {
        "source": "~/.codex/sessions rollouts matched by run-project cwd and run time",
        "threads": summary,
        "subagents": sum(1 for item in summary if item["thread_source"] == "subagent"),
        "subagents_of_lead": sum(1 for item in summary if item["parent_thread_id"] in roots),
        "max_depth": max((item["depth"] or 0 for item in summary), default=0),
    }
    text = json.dumps(facts, indent=2, ensure_ascii=False)
    user = Path.home().name
    text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", "<user>", text, flags=re.I)
    facts = json.loads(text)
    if args.write:
        result.setdefault("acceptance", {})["codex_threads"] = facts
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in facts.items() if key != "threads"}, indent=2))
    return 0 if threads else 1


if __name__ == "__main__":
    sys.exit(main())
