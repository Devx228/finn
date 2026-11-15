"""Export sanitized user/assistant text from local Claude Code and Codex session archives.

Tool calls, tool outputs, hidden reasoning, system/developer messages and account metadata are
deliberately omitted. The resulting Markdown is suitable for the challenge build-history folder;
run the repository secret scans before publishing it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "build-log"
HOME = Path.home()

SESSION_NOTES = {
    "claude-2026-11-12-49d4d2af.md": (
        "12 Nov",
        "Build and deploy the Push spine, then start Pull",
        "Deployed brief/cards and advanced through Phase 3",
        "NSE refused the campus origin; the agent stopped, recorded the refusal and used the documented worker/cache path",
    ),
    "claude-2026-11-12-7395748e.md": (
        "12–14 Nov",
        "Finish research, network and live generalisation",
        "Promise Ledger, network actions and live job queue shipped",
        "POLYCAB produced four false verdicts; they became general exclusion rules and regression tests",
    ),
    "codex-2026-11-13-11bb4b85.md": (
        "14 Nov",
        "Resume and audit the interrupted build",
        "State checked; interrupted turn preserved for recovery",
        "The run was interrupted, so the next session inspected git state before repeating any mutation",
    ),
    "codex-2026-11-13-2b2ea733.md": (
        "14 Nov",
        "Critique submission readiness and choose the highest-value work",
        "Stale submission docs and the demo route were prioritised",
        "The first instinct to add features was rejected after the audit showed finished work was described as missing",
    ),
    "codex-2026-11-13-89a9b0ed.md": (
        "14–15 Nov",
        "Ship steps 1–9 and prepare the final submission",
        "Command bar, Push, onboarding, pre-call/audit cards, design pass and live generalisation shipped",
        "First-device Push subscribed before worker activation; fixed by awaiting the active registration and adding a regression test",
    ),
}

REDACTIONS = {
    "Google API key": r"AIza[0-9A-Za-z_-]{30,}",
    "Groq key": r"gsk_[0-9A-Za-z]{20,}",
    "GitHub token": r"(?:ghp|gho|ghs|ghu)_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,}",
    "Neon password": r"npg_[0-9A-Za-z]{10,}",
    "OpenAI-style key": r"\bsk-[0-9A-Za-z]{20,}",
    "database credentials": r"postgres(?:ql)?://[^\s'\"]+",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}


def clean(text: str) -> str:
    text = text.replace(str(HOME), "%USERPROFILE%").replace(str(HOME).replace("\\", "/"), "%USERPROFILE%")
    for label, pattern in REDACTIONS.items():
        text = re.sub(pattern, f"[REDACTED: {label}]", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def write_transcript(path: Path, title: str, source: str, entries: list[tuple[str, str, str]]) -> None:
    lines = [
        f"# {title}",
        "",
        f"> Source archive: `{source}`. Exported text only; tool calls/results, hidden reasoning,",
        "> system instructions and machine/account metadata are omitted. Secret patterns and the",
        "> local home-directory prefix are redacted.",
        "",
    ]
    for timestamp, role, text in entries:
        lines.extend((f"## {timestamp or 'timestamp unavailable'} — {role}", "", clean(text), ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def export_claude() -> list[tuple[str, str, int]]:
    folder = HOME / ".claude" / "projects" / "C--Users-devan-OneDrive-Desktop-enam-afe"
    exported = []
    if not folder.exists():
        return exported
    for source in sorted(folder.glob("*.jsonl")):
        entries: list[tuple[str, str, str]] = []
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                if item.get("isSidechain"):
                    continue
                message = item.get("message") or {}
                content = message.get("content")
                if item.get("type") == "user" and isinstance(content, str) and content.strip():
                    entries.append((item.get("timestamp", ""), "User", content))
                elif item.get("type") == "assistant" and isinstance(content, list):
                    texts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
                    ]
                    if texts:
                        entries.append((item.get("timestamp", ""), "Claude Code", "\n\n".join(texts)))
        if not entries:
            continue
        date = entries[0][0][:10] or "undated"
        name = f"claude-{date}-{source.stem[:8]}.md"
        write_transcript(OUT / name, f"Claude Code session — {date}", source.name, entries)
        exported.append((name, "Claude Code", len(entries)))
    return exported


def export_codex() -> list[tuple[str, str, int]]:
    folder = HOME / ".codex" / "sessions" / "2026"
    exported = []
    if not folder.exists():
        return exported
    for source in sorted(folder.rglob("*.jsonl")):
        entries: list[tuple[str, str, str]] = []
        mentions_repo = False
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                payload = item.get("payload") or {}
                if "enam-afe" in line:
                    mentions_repo = True
                if payload.get("type") != "message" or payload.get("role") not in {"user", "assistant"}:
                    continue
                texts = [
                    block.get("text", "")
                    for block in payload.get("content", [])
                    if isinstance(block, dict)
                    and block.get("type") in {"input_text", "output_text"}
                    and block.get("text")
                ]
                if texts:
                    role = "User" if payload["role"] == "user" else "Codex"
                    entries.append((item.get("timestamp", ""), role, "\n\n".join(texts)))
        if not mentions_repo or not entries:
            continue
        date = entries[0][0][:10] or "undated"
        session = source.stem.rsplit("-", 1)[-1][:8]
        name = f"codex-{date}-{session}.md"
        write_transcript(OUT / name, f"Codex session — {date}", source.name, entries)
        exported.append((name, "Codex", len(entries)))
    return exported


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exported = export_claude() + export_codex()
    rows = []
    for name, tool, messages in exported:
        date, goal, outcome, correction = SESSION_NOTES.get(
            name, ("see export", "See export", "See export", "See export")
        )
        rows.append(
            f"| {date} | [{name}]({name}) | {tool} | {goal} | {outcome} | {correction} | {messages} |"
        )
    row_text = "\n".join(rows)
    readme = f"""# AI build history

FINN was built through long-running Claude Code and Codex sessions, with decisions and failures
recorded as they happened. These exports contain the visible user/assistant conversation only;
tool traffic and hidden reasoning are excluded to avoid publishing machine metadata, cached source
documents or credentials.

| Date (IST) | Export | Tool | Goal | Outcome | Where the model/tool was wrong; correction | Visible messages |
|---|---|---|---|---|---|---:|
{row_text}

## How to read the history

- [DECISIONS.md](../DECISIONS.md) is the dated decision record, including rejected alternatives.
- [PROGRESS.md](../../PROGRESS.md) is the checkpoint trail across agent sessions.
- [evals.md](../evals.md) records measured failures and regression sets.
- The most consequential correction is documented in the sessions and decisions: the first live
  POLYCAB report produced four false verdicts; those failures became general rules and tests rather
  than ticker-specific patches.

The exporter is [`scripts/export_build_history.py`](../../scripts/export_build_history.py). Run it
locally to regenerate these files, then run both secret scans before publishing.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"exported {len(exported)} session transcripts to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
