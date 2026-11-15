# AI build history

FINN was built through long-running Claude Code and Codex sessions, with decisions and failures
recorded as they happened. These exports contain the visible user/assistant conversation only;
tool traffic and hidden reasoning are excluded to avoid publishing machine metadata, cached source
documents or credentials.

| Date (IST) | Export | Tool | Goal | Outcome | Where the model/tool was wrong; correction | Visible messages |
|---|---|---|---|---|---|---:|
| 12 Nov | [claude-2026-11-12-49d4d2af.md](claude-2026-11-12-49d4d2af.md) | Claude Code | Build and deploy the Push spine, then start Pull | Deployed brief/cards and advanced through Phase 3 | NSE refused the campus origin; the agent stopped, recorded the refusal and used the documented worker/cache path | 143 |
| 12–15 Nov | [claude-2026-11-12-7395748e.md](claude-2026-11-12-7395748e.md) | Claude Code | Finish research, network and live generalisation | Promise Ledger, network actions and live job queue shipped | POLYCAB produced four false verdicts; they became general exclusion rules and regression tests | 321 |
| 14 Nov | [codex-2026-11-13-11bb4b85.md](codex-2026-11-13-11bb4b85.md) | Codex | Resume and audit the interrupted build | State checked; interrupted turn preserved for recovery | The run was interrupted, so the next session inspected git state before repeating any mutation | 8 |
| 14 Nov | [codex-2026-11-13-2b2ea733.md](codex-2026-11-13-2b2ea733.md) | Codex | Critique submission readiness and choose the highest-value work | Stale submission docs and the demo route were prioritised | The first instinct to add features was rejected after the audit showed finished work was described as missing | 11 |
| 14–15 Nov | [codex-2026-11-13-89a9b0ed.md](codex-2026-11-13-89a9b0ed.md) | Codex | Ship steps 1–9 and prepare the final submission | Command bar, Push, onboarding, pre-call/audit cards, design pass and live generalisation shipped | First-device Push subscribed before worker activation; fixed by awaiting the active registration and adding a regression test | 120 |

## How to read the history

- [DECISIONS.md](../DECISIONS.md) is the dated decision record, including rejected alternatives.
- [PROGRESS.md](../../PROGRESS.md) is the checkpoint trail across agent sessions.
- [evals.md](../evals.md) records measured failures and regression sets.
- The most consequential correction is documented in the sessions and decisions: the first live
  POLYCAB report produced four false verdicts; those failures became general rules and tests rather
  than ticker-specific patches.

The exporter is [`scripts/export_build_history.py`](../../scripts/export_build_history.py). Run it
locally to regenerate these files, then run both secret scans before publishing.
