# Mini-PRD: API key management for Acme's webhook service

Repo: acme/webhook-svc (Python/FastAPI, Postgres, Alembic). Check command:
`bash scripts/check.sh`. Baseline is green.

We need customer-managed API keys for the webhook admin API:

1. A new `api_keys` table: id, org_id (FK), key_hash, label, created_at,
   revoked_at (nullable). Keys are shown once at creation, stored hashed.
2. CRUD endpoints under `/v1/api-keys`: create (returns plaintext once),
   list (no hashes), revoke. Org-scoped: a key only sees its own org's keys.
3. Auth middleware accepts `Authorization: Bearer <key>` on all `/v1/*`
   routes, resolving to the org; revoked keys are rejected with 401.
4. Rate limiting per key: 100 req/min default, configurable per key via a
   `rate_limit` column; enforced in middleware, returns 429 + Retry-After.
5. Audit log: every key creation/revocation writes an `audit_events` row.

Constraints: never log plaintext keys; hashing must use the repo's existing
`hash_secret()` helper; middleware changes must not break the existing
session-cookie auth path (both must work side by side).
