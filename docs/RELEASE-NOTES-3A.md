# Phase 3 Batch A — release notes (ops: degraded state)

## Release order — workspace `run-job.sh` BEFORE cinema `main` gets this `run.sh`

Task A1 ships two halves of one mechanism, in two independently-deployed repos:

- `saas/cinema` (`run.sh`, branch `phase3a`): a still-bad, already-alerted condition (pull/tests/
  refresh/deploy/memory-wait) now exits **78** (`DEGRADED_RC`) instead of the old silent `0`.
- `workspace` (`automation/phone/run-job.sh`, commit `2a8e9d1` + the round-1 fix on top): `finish()`
  now treats rc **78** — and only 78 — as `status=degraded` (no notification; the job already sent
  its own reminder). Any other non-zero rc still goes through the old `failed` path (`write_state
  failed`, notify).

**Both files must land on the Fold before `run.sh`'s new exit code reaches production**, in this
order:

1. `automation/phone/run-job.sh` (workspace) reaches the Fold first — `wsync`, or `git pull
   --ff-only` in `/root/workspace` by hand.
2. Only then may `saas/cinema`'s `phase3a` (with this task's `run.sh`) merge into cinema's `main`
   and reach the Fold.

**Why the order matters (the hazard, unmitigated by any code in this diff):** if `run.sh`'s exit-78
change reaches the Fold's `saas/cinema/main` while the Fold's `run-job.sh` is still the *old*
version (only `ok`/`failed`, no rc==78 branch), every degraded tick reads as a **fresh failure**:
`write_state failed 78 ...` **and** `notify "... FAILED rc=78 ..."` — on every run for as long as
the condition lasts. That is an alert-storm in the *opposite* direction from what this task exists
to prevent (the old bug was silence; this reversal would be noise), for the entire window between
the two deploys.

Reversing the order is harmless: an updated `run-job.sh` with no rc==78 branch would simply never
see it from an *old* `run.sh` (which still exits `0`/`3`/`6`/`7` for its conditions, unchanged
until `phase3a` merges) — no behavior change, no risk.

## Sequencing — controller's responsibility

This note documents the hazard and the required order; the controller sequences the actual
deploys (workspace pull, then cinema merge/deploy) and confirms each landed on the Fold before
triggering the next. No code change in `phase3a` or `run-job.sh` enforces this ordering — it is a
two-repo deployment concern, not something a single diff can gate.

## Exit code registry (so a future change doesn't repeat this collision)

| code | meaning | where |
|---|---|---|
| 0 | ok | universal |
| 2 | run-job.sh: unknown job name (pre-existing, unrelated to this task) | `run-job.sh` |
| 3 | cinema run.sh: deploy.sh failed | `saas/cinema/run.sh` |
| 6 | cinema run.sh: test suite failed | `saas/cinema/run.sh` |
| 7 | cinema run.sh: git pull failed | `saas/cinema/run.sh` |
| **78** | **DEGRADED — an already-alerted failure is still going on** (docs/RULINGS.md:37) | `saas/cinema/run.sh` (`fail()`), `run-job.sh` (`finish()`, `DEGRADED_RC`) |
| 75 | run-job.sh: wait_for_mem timed out (no alerts.py to hand off to) | `run-job.sh` |
| 9 | tifo job: health feed stale/failing | `run-job.sh` (`tifo` case) |

`DEGRADED_RC` is a single constant in each file (`run.sh` top-of-file, `run-job.sh` near the top) —
change it in exactly those two places, together, if it ever needs to move again.
