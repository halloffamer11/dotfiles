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

**Status:** ready-for-agent

- [ ] `grep -n 'catalog\._' tools/delegate-dashboard/*.py` prints nothing.
- [ ] A `test_catalog.py` case pins the public function's fields and that it writes
      nothing.
- [ ] `test_dashboard.py` and every suite under `agents/skills/delegate/tests/` exit 0.
- [ ] The byte-for-byte save test of ticket 13 still passes unchanged.
