"""Append-only, human-readable run log (RUN_LOG.md). Failures are recorded, never hidden."""
from __future__ import annotations

from pathlib import Path

from .sources.base import now_iso


class RunLog:
    def __init__(self, path: Path, mode: str):
        self.path = path
        self.mode = mode
        self.started = now_iso()
        self.sections: list[tuple[str, list[str]]] = []

    def section(self, title: str, lines: list[str] | str) -> None:
        self.sections.append((title, [lines] if isinstance(lines, str) else list(lines)))
        print(f"\n== {title}")
        for ln in ([lines] if isinstance(lines, str) else lines):
            print(f"   {ln}")

    def write(self) -> None:
        out = [f"\n---\n\n## Run {self.started} — mode `{self.mode}`\n", f"Finished: {now_iso()}\n"]
        for title, lines in self.sections:
            out.append(f"\n### {title}\n")
            out.extend(f"- {ln}" if not ln.startswith("|") else ln for ln in lines)
            out.append("")
        header = ""
        if not self.path.exists():
            header = ("# RUN_LOG\n\nEvery pipeline run appends a section below: sources attempted, what failed and why, "
                      "counts, cost, exchange rate, assumptions and checks. Nothing is removed.\n")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(header + "\n".join(out) + "\n")
