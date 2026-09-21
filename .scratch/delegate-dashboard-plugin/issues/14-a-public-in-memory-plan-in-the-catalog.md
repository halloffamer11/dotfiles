# 14 — A public in-memory plan in the catalog

**What to build:** the dashboard's staged view (ticket 13) builds a catalog from documents
that are not on disk. It does that through three private helpers of
`agents/skills/delegate/scripts/catalog.py`: `_plan_order`, `_plan_set` and
`_catalog_from_docs`, and it reads their results by tuple position (`planned[3]`,
`planned[4]`). A refactor inside `catalog.py` can break staging with no failing delegate
test. Found by the independent review of ticket 13, 2026-09-20.

**Blocked by:** 13 Staged edits and one save

## Scope

- `catalog.py` gains one public function that takes the source documents and a list of
  edit operations (the same operations `edit_catalog` accepts) and returns the planned
  documents and the effective catalog, as named fields. It writes nothing and reads no
  Meter. `edit_catalog` uses it, so there is one planning path.
- `tools/delegate-dashboard/model.py` calls only that function; no `catalog._` name is
  left in the dashboard.
- No behaviour change: the same edits give the same bytes and the same ranking.

## Acceptance

**Status:** implemented 2026-09-20 (`acb64c5`) on `worktree/delegate-dashboard-plugin`; all boxes ticked. The merge to `main` is Orin's.

- [x] `grep -n 'catalog\._' tools/delegate-dashboard/*.py` prints nothing.
- [x] A `test_catalog.py` case pins the public function's fields and that it writes
      nothing.
- [x] `test_dashboard.py` and every suite under `agents/skills/delegate/tests/` exit 0.
- [x] The byte-for-byte save test of ticket 13 still passes unchanged.

## Landed, 2026-09-20

`acb64c5`. Ranked `/delegate run impl --tier 3`: codex and grok were under the Gate, and
`opus-high@claude` was the pick. Run `20260921T014604Z-opus-high@claude-095c3f7c`, about
400 s, verdict clean.

`catalog.plan_edits(ops, lanes_doc, routing_doc, project_doc, files, project_lanes_doc=None)`
plans each operation onto the result of the one before it and returns the named fields
`lanes`, `routing`, `project`, `project_lanes`, `catalog` and `steps`. It reads no file and
no Meter, writes nothing and does not change its inputs. `edit_catalog` plans its one edit
through it. In the dashboard `_replay` is gone and `_staged_plan` is the only planning call.
`test_catalog.py` gained cases 15.1-15.8, written first; one pins the planned bytes against
what `edit_catalog` writes.

Checked by the session: the `catalog\._` grep over `tools/delegate-dashboard/*.py` prints
nothing; `test_dashboard.py` runs 66 tests, `OK`; every suite under
`agents/skills/delegate/tests/` exits 0; `catalog.py check` on the stowed catalog still ends
`ok`; a live `catalog.py set routing.margin 0.2 --scope global` preview returns the same
fields as before and writes nothing.
