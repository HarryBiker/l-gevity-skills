"""Acceptance facts from a recorded agent stream (Claude Code stream-json or
`codex exec --json`). Pure functions over a list of (seconds, event) pairs, so
the same code analyses a live run, a saved .stream.jsonl, and the synthetic
parser fixtures under .pilot/test/. Stdlib only.

Ordering facts (overlap, review after implementation) are decided on stream
order, the event index; seconds are reported alongside for reading.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SKILL_PATH_RE = re.compile(r"[\\/]?skills[\\/]([A-Za-z0-9_.-]+)[\\/]SKILL\.md\b")
EXECUTION_RE = re.compile(r"^[\s>*_`|-]*Execution:[\s*_`]*(.+?)[\s*_`|]*$", re.M)
DISPATCH_RE = re.compile(r"Dispatch:[\s*_`]*(SKIP|DIRECT|ADAPTIVE|FULL)\b")
MODE_RE = re.compile(r"\b(single-agent|multi-agent)\b")
CHECK_RE = re.compile(r"check_orchestration\.py[\"']?\s+([a-z_-]+)")
EXIT_RE = re.compile(r"[Ee]xit code:?\s*(-?\d+)")
VERDICT_RE = re.compile(r"\b(PASS|FAIL|ESCALATE|ACCEPT|REJECT|STALE|RETRY)\b")
AGENT_ID_RE = re.compile(r"agent[ _-]?[Ii][Dd]\W{0,3}\s*([A-Za-z0-9_-]{4,})")
AGENT_TOOLS = {"Agent", "Task"}
SHELL_TOOLS = {"Bash", "PowerShell"}
INJECTED_MESSAGE = "simulated agent crash"
CODEX_TYPE_KEYS = ("agent_type", "subagent_type", "agent", "role", "agent_name", "name")
CODEX_FINISH_TOOLS = {"wait", "wait_agent", "close_agent"}


def load_stream(path: Path) -> list[tuple[float | None, dict]]:
    """Read JSONL; each event may carry `_t` (seconds since start)."""
    stamped = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            stamped.append((event.get("_t"), event))
    return stamped


def text_of(content) -> str:
    """Flatten a tool_result or message content into text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return json.dumps(content)


def role_of(subagent_type: str) -> str:
    lowered = (subagent_type or "").lower()
    if "implementer" in lowered:
        return "implementer"
    if "analyst" in lowered or "review" in lowered or "verif" in lowered:
        return "analyst"
    return "other"


def skills_in(text: str) -> list[str]:
    return [match.group(1) for match in SKILL_PATH_RE.finditer(text or "")]


def execution_facts(texts: list[str]) -> dict:
    joined = "\n\n".join(texts)
    lines = [match.group(1).strip() for match in EXECUTION_RE.finditer(joined)]
    dispatch = DISPATCH_RE.search(joined)
    mode = next((m.group(1) for line in lines for m in [MODE_RE.search(line)] if m), None)
    return {
        "execution_line": lines[0] if lines else None,
        "execution_lines": lines,
        "execution_mode": mode,
        "dispatch": dispatch.group(1) if dispatch else None,
    }


def ordering_facts(launches: list[dict]) -> dict:
    """Overlap, review-after-implementation, and correction-after-review on stream order."""
    live = [launch for launch in launches if not launch["blocked"]]
    overlap = False
    unknown = False
    for i, first in enumerate(live):
        for second in live[i + 1:]:
            if first["finish_index"] is None:
                unknown = True
            elif second["launch_index"] < first["finish_index"]:
                overlap = True
    implementers = [launch for launch in live if launch["role"] == "implementer"]
    analysts = [launch for launch in live if launch["role"] == "analyst"]
    reviews = []
    for analyst in analysts:
        prior = [impl for impl in implementers if impl["launch_index"] < analyst["launch_index"]]
        if prior and all(
            impl["finish_index"] is not None and impl["finish_index"] < analyst["launch_index"] for impl in prior
        ):
            reviews.append(analyst)
    corrections = []
    for review in reviews:
        boundary = review["finish_index"] if review["finish_index"] is not None else review["launch_index"]
        corrections.extend(
            impl["tool_use_id"] for impl in implementers if impl["launch_index"] > boundary
        )
    return {
        "parallel_overlap": True if overlap else (None if unknown else False),
        "review_after_implementation": bool(reviews),
        "review_launches": [review["tool_use_id"] for review in reviews],
        "correction_after_review": bool(corrections),
        "correction_launches": sorted(set(corrections)),
    }


def analyze_claude(stamped: list[tuple[float | None, dict]]) -> dict:
    """Facts from a Claude Code `--output-format stream-json --verbose` run."""
    census: Counter = Counter()
    init: dict = {}
    result: dict | None = None
    tool_uses: dict[str, dict] = {}
    tool_results: dict[str, dict] = {}
    activity: dict[str, list[int]] = defaultdict(list)
    notifications: list[tuple[int, str]] = []
    lead_texts: list[str] = []
    skill_loads: dict[str | None, list[str]] = defaultdict(list)
    tool_counts: dict[str, Counter] = {"lead": Counter(), "subagents": Counter()}

    for index, (_, event) in enumerate(stamped):
        kind, subtype = event.get("type"), event.get("subtype")
        census[f"{kind}/{subtype}" if subtype else str(kind)] += 1
        parent = event.get("parent_tool_use_id")
        raw = json.dumps(event)
        if parent:
            activity[parent].append(index)
        if "task-notification" in raw or "task_notification" in raw:
            notifications.append((index, raw))
        if kind == "system":
            if subtype == "init":
                init = event
            if event.get("tool_use_id"):
                activity[event["tool_use_id"]].append(index)
        elif kind == "result":
            result = event
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and not parent:
                    lead_texts.append(str(block.get("text", "")))
                if block.get("type") != "tool_use":
                    continue
                name, arguments = block.get("name"), block.get("input") or {}
                tool_counts["subagents" if parent else "lead"][name] += 1
                tool_uses[block.get("id")] = {"name": name, "input": arguments, "parent": parent, "index": index}
                if name == "Skill":
                    skill_loads[parent].append(str(arguments.get("skill", "")))
                elif name == "Read":
                    skill_loads[parent].extend(skills_in(str(arguments.get("file_path", ""))))
                elif name in SHELL_TOOLS:
                    skill_loads[parent].extend(skills_in(str(arguments.get("command", ""))))
        elif kind == "user":
            content = (event.get("message") or {}).get("content")
            blocks = content if isinstance(content, list) else []
            results = [block for block in blocks if isinstance(block, dict) and block.get("type") == "tool_result"]
            structured = event.get("tool_use_result")
            for block in results:
                tool_results[block.get("tool_use_id")] = {
                    "index": index,
                    "is_error": bool(block.get("is_error")),
                    "text": text_of(block.get("content")),
                    "structured": structured if len(results) == 1 else None,
                }

    times = [t for t, _ in stamped]

    def at(index):
        return times[index] if index is not None and index < len(times) else None

    launches = []
    for tool_use_id, use in sorted(tool_uses.items(), key=lambda item: item[1]["index"]):
        if use["name"] not in AGENT_TOOLS:
            continue
        returned = tool_results.get(tool_use_id)
        text = returned["text"] if returned else ""
        blocked = bool(returned and returned["is_error"] and INJECTED_MESSAGE in text)
        agent_id = AGENT_ID_RE.search(text)
        agent_id = agent_id.group(1) if agent_id else None
        background = bool(use["input"].get("run_in_background")) or bool(
            agent_id and re.search(r"(?i)async|background", text)
        )
        candidates = []
        if returned and (not background or blocked):
            candidates.append(returned["index"])
        if activity.get(tool_use_id):
            candidates.append(max(activity[tool_use_id]))
        if background and not blocked:
            keys = [key for key in (agent_id, tool_use_id) if key]
            notice = next(
                (idx for idx, raw in notifications if idx > use["index"] and any(key in raw for key in keys)), None
            )
            if notice is not None:
                candidates.append(notice)
        finish = max(candidates) if candidates else None
        subagent_type = str(use["input"].get("subagent_type") or "general-purpose")
        launches.append({
            "tool_use_id": tool_use_id,
            "order": len(launches),
            "subagent_type": subagent_type,
            "role": role_of(subagent_type),
            "description": str(use["input"].get("description", ""))[:200],
            "launched_by": use["parent"] or "lead",
            "background": background,
            "blocked": blocked,
            "is_error": bool(returned and returned["is_error"]),
            "launch_index": use["index"],
            "finish_index": finish,
            "launched_at": at(use["index"]),
            "finished_at": at(finish),
            "subagent_events": len(activity.get(tool_use_id, [])),
        })

    checks = []
    for tool_use_id, use in sorted(tool_uses.items(), key=lambda item: item[1]["index"]):
        command = str(use["input"].get("command", ""))
        if use["name"] not in SHELL_TOOLS or "check_orchestration.py" not in command:
            continue
        returned = tool_results.get(tool_use_id)
        status = None
        if returned:
            structured = returned.get("structured") if isinstance(returned.get("structured"), dict) else {}
            code = structured.get("exitCode", structured.get("returnCode"))
            match = EXIT_RE.search(returned["text"])
            if isinstance(code, int):
                status = code
            elif match:
                status = int(match.group(1))
            else:
                status = "nonzero" if returned["is_error"] else 0
        verdict = VERDICT_RE.search(returned["text"]) if returned else None
        subcommand = CHECK_RE.search(command)
        checks.append({
            "kind": subcommand.group(1) if subcommand else None,
            "command": command,
            "run_by": use["parent"] or "lead",
            "exit_status": status,
            "verdict": verdict.group(1) if verdict else None,
            "at": at(use["index"]),
        })

    launch_ids = {launch["tool_use_id"] for launch in launches}
    subagent_events = sum(len(activity.get(tool_use_id, [])) for tool_use_id in launch_ids)
    by_subagent = {
        tool_use_id: sorted(set(skill_loads.get(tool_use_id, []))) for tool_use_id in sorted(launch_ids)
    }
    blocked = [launch for launch in launches if launch["blocked"]]
    retry = next(
        (launch for launch in launches if blocked and not launch["blocked"] and launch["order"] > blocked[0]["order"]),
        None,
    )
    acceptance = {
        "agent_launches": launches,
        "agent_launch_count": len([launch for launch in launches if not launch["blocked"]]),
        **ordering_facts(launches),
        "skills_loaded_by_lead": sorted(set(skill_loads.get(None, []))),
        "skills_loaded_by_subagents": by_subagent if (subagent_events or not launches) else None,
        "subagent_events_observed": subagent_events,
        **execution_facts(lead_texts),
        "orchestration_checks": checks,
        "injected_failure": {
            "blocked_launches": len(blocked),
            "retried": retry is not None,
            "retry_same_subagent_type": bool(retry and retry["subagent_type"] == blocked[0]["subagent_type"]),
            "retry_tool_use_id": retry["tool_use_id"] if retry else None,
        },
    }
    metrics = {}
    if result is not None:
        metrics = {
            key: result.get(key)
            for key in (
                "subtype", "is_error", "duration_ms", "duration_api_ms", "num_turns",
                "total_cost_usd", "usage", "modelUsage",
            )
        }
    return {
        "runtime": "claude",
        "init": {
            "model": init.get("model"),
            "claude_code_version": init.get("claude_code_version"),
            "permission_mode": init.get("permissionMode"),
            "tools": init.get("tools"),
            "skills": init.get("skills"),
            "agents": init.get("agents"),
        },
        "result_event": result is not None,
        "metrics": metrics,
        "tool_calls": {key: dict(value) for key, value in tool_counts.items()},
        "acceptance": acceptance,
        "census": dict(sorted(census.items())),
    }


def codex_receivers(item: dict) -> list[str]:
    found = []
    for key in ("receiver_thread_ids", "receiver_thread_id", "new_thread_id", "thread_id", "agent_id", "agent_ids"):
        value = item.get(key)
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            found.extend(str(entry) for entry in value if entry)
    return found


def analyze_codex(stamped: list[tuple[float | None, dict]]) -> dict:
    """Facts from a `codex exec --json` run. The collab item field names are
    read defensively; collab_item_keys reports the ones the run produced."""
    census: Counter = Counter()
    item_types: Counter = Counter()
    items: dict[str, dict] = {}
    usage: Counter = Counter()
    errors: list[str] = []
    thread_id = None
    collab_keys: set[str] = set()

    for index, (_, event) in enumerate(stamped):
        kind = str(event.get("type"))
        census[kind] += 1
        if kind == "thread.started":
            thread_id = event.get("thread_id")
        elif kind == "turn.completed":
            for key, value in (event.get("usage") or {}).items():
                if isinstance(value, (int, float)):
                    usage[key] += value
        elif kind in ("turn.failed", "error"):
            errors.append(str((event.get("error") or {}).get("message") or event.get("message") or ""))
        elif kind.startswith("item."):
            item = event.get("item") or {}
            item_id = str(item.get("id"))
            record = items.setdefault(item_id, {"first_index": index, "item": item, "completed_index": None})
            record["item"] = {**record["item"], **item}
            if kind == "item.completed":
                record["completed_index"] = index
            if item.get("type") == "collab_tool_call":
                collab_keys.update(item.keys())

    times = [t for t, _ in stamped]

    def at(index):
        return times[index] if index is not None and index < len(times) else None

    ordered = sorted(items.values(), key=lambda record: record["first_index"])
    for record in ordered:
        item_types[str(record["item"].get("type"))] += 1

    collab = [record for record in ordered if record["item"].get("type") == "collab_tool_call"]
    launches = []
    for record in collab:
        item = record["item"]
        if item.get("tool") != "spawn_agent":
            continue
        receivers = codex_receivers(item)
        finish = None
        for later in collab:
            if later["first_index"] <= record["first_index"] or later["item"].get("tool") not in CODEX_FINISH_TOOLS:
                continue
            if any(receiver in json.dumps(later["item"]) for receiver in receivers):
                finish = later["completed_index"] if later["completed_index"] is not None else later["first_index"]
                break
        prompt = str(item.get("prompt") or "")
        subagent_type = next((str(item[key]) for key in CODEX_TYPE_KEYS if item.get(key)), None)
        if subagent_type is None:
            named = re.search(r"alchemy-(implementer|analyst)", prompt)
            subagent_type = named.group(0) if named else "default"
        launches.append({
            "tool_use_id": str(item.get("id")),
            "order": len(launches),
            "subagent_type": subagent_type,
            "role": role_of(subagent_type),
            "description": prompt[:200],
            "launched_by": "lead",
            "background": True,
            "blocked": False,
            "is_error": item.get("status") in ("failed", "errored"),
            "receiver_thread_ids": receivers,
            "launch_index": record["first_index"],
            "finish_index": finish,
            "launched_at": at(record["first_index"]),
            "finished_at": at(finish),
            "subagent_events": None,
        })

    lead_texts, skills, checks = [], [], []
    for record in ordered:
        item = record["item"]
        if item.get("type") == "agent_message":
            lead_texts.append(str(item.get("text", "")))
        elif item.get("type") == "command_execution":
            command = str(item.get("command", ""))
            skills.extend(skills_in(command))
            if "check_orchestration.py" in command:
                subcommand = CHECK_RE.search(command)
                verdict = VERDICT_RE.search(str(item.get("aggregated_output", "")))
                checks.append({
                    "kind": subcommand.group(1) if subcommand else None,
                    "command": command,
                    "run_by": "lead",
                    "exit_status": item.get("exit_code"),
                    "verdict": verdict.group(1) if verdict else None,
                    "at": at(record["first_index"]),
                })

    acceptance = {
        "agent_launches": launches,
        "agent_launch_count": len(launches),
        **ordering_facts(launches),
        "skills_loaded_by_lead": sorted(set(skills)),
        "skills_loaded_by_subagents": None,
        "subagent_events_observed": None,
        **execution_facts(lead_texts),
        "orchestration_checks": checks,
        "injected_failure": None,
        "finish_basis": "first later wait/close_agent collab item naming the spawned thread",
    }
    return {
        "runtime": "codex",
        "init": {"thread_id_present": thread_id is not None},
        "result_event": "turn.completed" in census,
        "metrics": {"usage": dict(usage), "errors": errors, "total_cost_usd": None},
        "tool_calls": {"lead": dict(item_types), "subagents": {}},
        "acceptance": acceptance,
        "collab_item_keys": sorted(collab_keys),
        "census": dict(sorted(census.items())),
    }


def analyze(stamped: list[tuple[float | None, dict]], runtime: str) -> dict:
    return analyze_codex(stamped) if runtime == "codex" else analyze_claude(stamped)
