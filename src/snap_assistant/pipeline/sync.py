"""Fetch every source, sanity-check it, cross-validate, store, and report."""
from __future__ import annotations

import fcntl
import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .links import build_graph
from .reconcile import CONFLICT, PENDING, Decision, reconcile
from .sources import CARD, DEFAULT_SOURCES, LOCATION, Record, Source, http_get_json
from .store import Store, now


@dataclass
class SanityRules:
    min_count: dict[str, int] = field(default_factory=lambda: {CARD: 300, LOCATION: 100})
    max_shrink: float = 0.10          # vs the same source's previous good run
    min_complete: float = 0.95        # share of card records with name/cost/power


@dataclass
class SourceResult:
    name: str
    ok: bool
    counts: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass
class SyncResult:
    run_id: int | None
    status: str
    sources: list[SourceResult]
    decisions: list[Decision]
    report: str
    game_patch: str | None
    new_issue_count: int = 0
    uncovered_keywords: dict[str, list[str]] = field(default_factory=dict)

    @property
    def noteworthy(self) -> bool:
        """Worth a notification: something changed, broke, or newly disagrees."""
        return (self.status != "ok" or any(d.touched for d in self.decisions)
                or self.new_issue_count > 0)


def check_sanity(records: dict[str, list[Record]], previous: dict[str, int] | None,
                 rules: SanityRules) -> str | None:
    for kind, minimum in rules.min_count.items():
        n = len(records.get(kind, []))
        if n < minimum:
            return f"only {n} {kind}s (expected at least {minimum})"
        if previous and previous.get(kind) and n < previous[kind] * (1 - rules.max_shrink):
            return f"{kind}s dropped from {previous[kind]} to {n} since the last good run"
    cards = records.get(CARD, [])
    complete = sum(1 for r in cards if r.name and r.cost is not None and r.power is not None)
    if cards and complete / len(cards) < rules.min_complete:
        return f"only {complete}/{len(cards)} cards have name, cost and power"
    return None


def uncovered_keywords(decisions: list[Decision]) -> dict[str, list[str]]:
    """Keywords in card/location text that the rules reference doesn't explain yet."""
    from ..knowledge import covers

    missing: dict[str, list[str]] = {}
    for d in decisions:
        for k in d.extra.get("keywords") or []:
            if not covers(k):
                missing.setdefault(k, []).append(d.name)
    return missing


def _version_key(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def sync(
    store: Store,
    sources: list[Source] = DEFAULT_SOURCES,
    fetch: Callable[[str], object] = http_get_json,
    overrides: dict | None = None,
    rules: SanityRules | None = None,
    raw_dir: Path | None = None,
    dry_run: bool = False,
) -> SyncResult:
    rules = rules or SanityRules()
    last = store.last_run()
    prev_counts = json.loads(last["sources"]) if last else {}

    good: dict[str, list[Record]] = {}
    results: list[SourceResult] = []
    for src in sources:
        try:
            raw = {kind: fetch(url) for kind, url in src.urls.items()}
            parsed = src.parse(raw)
            res = SourceResult(src.name, True, {k: len(v) for k, v in parsed.items()})
            problem = check_sanity(parsed, prev_counts.get(src.name, {}).get("counts"), rules)
            if problem:
                res.ok, res.error = False, f"failed sanity check: {problem}"
            else:
                good[src.name] = [r for recs in parsed.values() for r in recs]
                if raw_dir and not dry_run:
                    _save_raw(raw_dir, src.name, raw)
        except Exception as e:
            res = SourceResult(src.name, False, error=str(e))
        results.append(res)

    names = [s.name for s in sources]
    down = {r.name for r in results if not r.ok}
    if not good:
        status = "failed"
        decisions: list[Decision] = []
    else:
        status = "ok" if not down else "partial"
        decisions = reconcile(good, store.priors(), names, down, overrides)

    patches = [d.extra["patch"] for d in decisions if d.extra.get("patch")]
    game_patch = max(patches, key=_version_key) if patches else None

    run_id = None
    new_issues = 0
    if dry_run:
        status = f"dry-run ({status})"
    else:
        old_issue_keys = {(r["kind"], r["def_id"], r["field"]) for r in store.issues()}
        run_id = store.start_run()
        if decisions:
            store.apply(run_id, decisions, build_graph(decisions, overrides))
        new_issues = sum(
            1 for d in decisions for f in (*d.conflicts, *d.held)
            if (d.kind, d.def_id, f) not in old_issue_keys
        )
        store.finish_run(
            run_id, status,
            {r.name: {"ok": r.ok, "counts": r.counts, "error": r.error} for r in results},
            _summary(decisions, game_patch),
        )

    result = SyncResult(run_id, status, results, decisions, "", game_patch, new_issues,
                        uncovered_keywords=uncovered_keywords(decisions))
    result.report = render_report(result)
    return result


def _summary(decisions: list[Decision], game_patch) -> dict:
    c = Counter(d.status for d in decisions)
    return {
        "game_patch": game_patch,
        "new": sum(d.is_new for d in decisions),
        "changed": sum(bool(d.changes) for d in decisions),
        "status_counts": dict(c),
    }


def _save_raw(raw_dir: Path, source: str, raw: dict):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for kind, payload in raw.items():
        with gzip.open(raw_dir / f"{source}-{kind}.json.gz", "wt") as f:
            json.dump(payload, f)


def _fmt(v) -> str:
    s = "∅" if v is None or v == "" else str(v)
    return s if len(s) <= 140 else s[:137] + "…"


def render_report(r: SyncResult, list_limit: int = 30) -> str:
    out = [f"# Snap data sync — {now()}", "", f"**Status:** {r.status}"]
    if r.game_patch:
        out.append(f"**Latest game patch in data:** {r.game_patch}")
    out.append("")
    for s in r.sources:
        counts = ", ".join(f"{n} {k}s" for k, n in s.counts.items())
        out.append(f"- {'✅' if s.ok else '❌'} **{s.name}** {counts}" + (f" — {s.error}" if s.error else ""))
    if "failed" in r.status:
        out += ["", "No source passed its checks, so nothing was changed."]
        return "\n".join(out) + "\n"

    ds = r.decisions
    new = [d for d in ds if d.is_new]
    changed = [d for d in ds if d.changes]
    conflicts = [d for d in ds if d.status == CONFLICT]
    held = [d for d in ds if d.status == PENDING]
    stale = [d for d in ds if d.stale_overrides]
    statuses = Counter(d.status for d in ds)
    out += ["", "**Totals:** " + ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))]

    def section(title, items, line):
        if not items:
            return
        out.extend(["", f"## {title} ({len(items)})"])
        for d in items[:list_limit]:
            out.extend(line(d))
        if len(items) > list_limit:
            out.append(f"- …and {len(items) - list_limit} more")

    label = lambda d: f"**{d.name}**" + (" (location)" if d.kind == LOCATION else "")
    section("Changed", changed, lambda d: [
        f"- {label(d)}: {c.field} {_fmt(c.old)} → {_fmt(c.new)} _[{c.how}"
        + (f", patch {d.extra['patch']}" if d.extra.get("patch") else "") + "]_"
        for c in d.changes])
    section("New", new, lambda d: [
        f"- {label(d)}" + (f" [{d.values.get('cost')}/{d.values.get('power')}]" if d.kind == CARD else "")
        + f" — {d.status}" + ("" if d.released else ", unreleased")])
    section("Conflicts — sources disagree, previous value kept", conflicts, lambda d: [
        f"- {label(d)} `{f}`: " + "; ".join(f"{s} says {_fmt(v)}" for s, v in vals.items())
        for f, vals in d.conflicts.items()])
    section("Awaiting confirmation from a second source", held, lambda d: [
        f"- {label(d)} `{f}`: " + "; ".join(f"{s} says {_fmt(v)}" for s, v in vals.items())
        + f" (keeping {_fmt(d.values.get(f))})"
        for f, vals in d.held.items()])
    section("Overrides the sources now agree with (safe to remove)", stale, lambda d: [
        f"- {label(d)}: {', '.join(d.stale_overrides)}"])
    if r.uncovered_keywords:
        out.extend(["", f"## Keywords missing from the rules reference ({len(r.uncovered_keywords)})",
                    "Add a section to src/snap_assistant/knowledge/rules.md:"])
        for k, names in sorted(r.uncovered_keywords.items()):
            out.append(f"- **{k}** — used by {', '.join(sorted(set(names))[:5])}"
                       + (f" and {len(set(names)) - 5} more" if len(set(names)) > 5 else ""))
    if not (new or changed or conflicts or held or stale):
        out += ["", "No changes."]
    return "\n".join(out) + "\n"


class RunLock:
    """Stop a scheduled run and a manual run from overlapping."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w")

    def __enter__(self):
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another sync is already running.") from None
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
