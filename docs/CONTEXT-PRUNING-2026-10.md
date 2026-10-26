# Context pruning audit (2026-10)

Goal: reduce noise for fresh sessions without deleting operational knowledge.

## Keep as canonical (active)

- `AGENTS.md`
- `profiles/README.md`
- `docs/START-HERE.md`
- `docs/profile-generation-manual-server.md`
- `docs/profile-login-procedure.md`
- `docs/profile-provisioning-mobile.md`
- `docs/re-droid-gotchas.md`
- `docs/bing-mobile-flow.md`

## Keep as historical decision records (read only when needed)

- `docs/ideas/2026-09-09-d3-tile-map.md`
- `docs/ideas/2026-09-09-mobile-daily-flow-d2.md`
- `docs/ideas/2026-09-09-points-reader-api.md`
- `docs/ideas/2026-09-09-web-to-mobile-migration.md`
- `docs/operations/2026-10-14-stabilization-plan.md`

## Candidate noise / artifacts

- local scratch notes such as `docs/new acc.md` (if not part of formal runbook)
- ad-hoc one-off command dumps not tied to runbooks
- duplicate instructions already covered in `START-HERE` + `profiles/README.md`

## Practical rule

If a file does not satisfy one of these, archive or remove it:

1. required to run/provision/recover production,
2. source of truth for schedule/registry,
3. post-incident decision record with reusable lessons.

