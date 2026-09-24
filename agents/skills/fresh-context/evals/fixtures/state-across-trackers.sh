#!/bin/sh
# Two trackers (a superpowers plan and a mattpocock-style issues folder). The
# session pasted a Status section into CLAUDE.md that copies both, plus one
# blocker that no tracker holds yet.
. "$(dirname "$0")/_lib.sh" "$1"

mkdir -p src docs/superpowers/plans .scratch/billing/issues
printf 'def login(u, p):\n    return u == "admin"\n' > src/auth.py
printf 'def charge(cents):\n    raise NotImplementedError\n' > src/billing.py
cat > docs/superpowers/plans/2026-09-15-auth.md <<'X'
# Auth plan
- [x] 1. Password hashing
- [x] 2. Session tokens
- [x] 3. Login endpoint
- [ ] 4. Logout endpoint
- [ ] 5. Rate-limit login attempts
X
cat > .scratch/billing/issues/01-invoices.md <<'X'
# 01: invoices
**Status:** landed
X
cat > .scratch/billing/issues/02-refunds.md <<'X'
# 02: refunds
**Status:** in progress. Partial refunds done; full refunds next.
X
cat > .scratch/billing/issues/03-stripe-webhooks.md <<'X'
# 03: Stripe webhooks
**Status:** ready
X
cat > CLAUDE.md <<'X'
# shopcore

Auth and billing for the shop.

## Commands
- Test: `python -m pytest -q`

## Conventions
- Money is integer cents.
- Never log a card number or a password, even masked.
X
base_commit "shopcore"

# --- this session (uncommitted) ---
cat >> CLAUDE.md <<'X'

## Status
- Auth (docs/superpowers/plans/2026-09-15-auth.md): steps 1-4 done as of 2026-09-23; step 5, rate-limit login attempts, is next.
- Billing 01 invoices: landed.
- Billing 02 refunds: in progress, partial refunds done, full refunds next.
- Billing 03 Stripe webhooks: blocked 2026-09-23. The Stripe test key in `.env.test` expired; the user must rotate it in the Stripe dashboard before webhook tests can run.

## Waiting on the user
- Rotate the Stripe test key.
X
