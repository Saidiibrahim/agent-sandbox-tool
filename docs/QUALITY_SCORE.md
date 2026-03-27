# Quality Score

- Owner: repository maintainers
- Last reviewed: 2026-03-27
- Review cadence: weekly or at the close of any major initiative

## Scorecard

| Area | Score (0-5) | Notes |
| --- | --- | --- |
| Architecture legibility | 4 | Layering is clear; new knowledge system is now repo-local. |
| Product clarity | 4 | Product charter and design goals are documented, but examples can grow. |
| Reliability evidence | 4 | Unit and integration paths are defined; live Modal coverage remains opt-in. |
| Security posture | 5 | Host-owned state and blocked-network defaults are explicit. |
| Planning discipline | 4 | Exec-plan validator exists; future work must keep plan/state in sync. |
| Documentation freshness | 4 | Canonical layout is in place; weekly doc-gardening should keep it current. |

## Rubric

- `5`: clear, current, and mechanically enforced
- `4`: good and reliable, with minor follow-up work
- `3`: usable but inconsistent or partially stale
- `2`: significant ambiguity or missing verification
- `1`: unreliable source of truth
- `0`: absent

## Action Item Expectations

- Every score below `4` needs a dated follow-up item in an active exec plan or the tech-debt tracker.
- Material regressions should update this file in the same change that introduces or fixes them.
- Quality changes should cite verification evidence, not only intuition.
