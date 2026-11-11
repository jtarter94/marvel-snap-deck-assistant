"""The rules reference (rules.md) as searchable sections."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

_META = re.compile(r"`([a-z]+):\s*([^`]*)`")


@dataclass
class Section:
    title: str
    part: str                 # Core rules | Keywords | Common mechanics ... | Interaction principles
    status: str
    aliases: list[str] = field(default_factory=list)
    verified: str | None = None
    body: str = ""

    def render(self) -> str:
        note = {"established": "", "from-card-text":
                " (worked out from card text; verify edge cases in-game)"}.get(self.status, f" ({self.status})")
        ver = f"; verified {self.verified}" if self.verified else ""
        return f"## {self.title}\n[{self.part}; status: {self.status}{ver}]{note}\n\n{self.body.strip()}\n"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9+]+", " ", s.lower()).strip()


@lru_cache(maxsize=1)
def sections() -> tuple[Section, ...]:
    text = resources.files(__package__).joinpath("rules.md").read_text()
    out: list[Section] = []
    part = ""
    cur: Section | None = None
    for line in text.splitlines():
        if line.startswith("# "):
            part = line[2:].strip()
            cur = None
            continue
        if line.startswith("## "):
            cur = Section(title=line[3:].strip(), part=part, status="unknown")
            out.append(cur)
            continue
        if cur is None:
            continue
        meta = dict(_META.findall(line)) if line.startswith("`status:") else {}
        if meta:
            cur.status = meta.get("status", cur.status).strip()
            cur.aliases = [a.strip() for a in meta.get("aliases", "").split(",") if a.strip()]
            cur.verified = meta.get("verified") or None
        else:
            cur.body += line + "\n"
    return tuple(out)


def _names(s: Section) -> set[str]:
    return {_norm(s.title), *(_norm(a) for a in s.aliases)} | (
        {_norm(p) for p in s.title.split(" and ")} if s.part == "Keywords" else set())


def lookup(topic: str) -> list[Section]:
    """Sections whose title/alias matches the topic; falls back to full-text search."""
    q = _norm(topic)
    exact = [s for s in sections() if q in _names(s)]
    if exact:
        return exact
    partial = [s for s in sections() if any(q in n or (n and n in q) for n in _names(s))]
    if partial:
        return partial
    words = q.split()
    return [s for s in sections() if words and all(w in _norm(s.title + " " + s.body) for w in words)]


def covers(keyword: str) -> bool:
    k = _norm(keyword)
    return any(k in _names(s) for s in sections())


def index() -> str:
    lines, part = [], None
    for s in sections():
        if s.part != part:
            part = s.part
            lines.append(f"{part}:")
        flag = "" if s.status == "established" else f"  [{s.status}]"
        lines.append(f"  - {s.title}{flag}")
    return "\n".join(lines)
