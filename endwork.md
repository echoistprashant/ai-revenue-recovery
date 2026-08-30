This is the final production-readiness push. Complete Phase 13, 14, and 15, and wire in the
real Gemini and Razorpay test-mode credentials that are now sitting in the local .env file.
Work through the blocks below in order. Checkpoint after EVERY block — run tests, confirm
green, commit, push, write/update the phase-notes entry — before moving to the next one.
Don't bundle multiple blocks into one uncommitted pile of changes, and don't skip a block's
verification just because the next block is waiting.

## Step 0 — verify preconditions before touching anything
- Run the full existing test suite and confirm everything through Phase 12 still passes
- Check that .env actually contains real-looking values for GEMINI_API_KEY, RAZORPAY_KEY_ID,
  RAZORPAY_WEBHOOK_SECRET, and RAZORPAY_KEY_SECRET (if provided) — not empty, not obviously
  a placeholder like "your_key_here"
- If either check fails, stop and tell me exactly what's wrong rather than proceeding or
  silently working around it

## Block 1 — Finish Phase 13 (Next.js frontend: code-complete but unverified today)
- Add vitest.config.ts and the missing unit test files
- Run `npm run verify` and get it fully green — fix whatever it surfaces
- Add frontend/Dockerfile and a frontend service in docker-compose.yml
- Add a CI job for the frontend (mirror the existing backend CI job's structure)
- Write docs/phase-notes/phase-13.md
- Commit and push only once npm run verify is actually green

## Block 2 — Phase 14: security, observability, PII hardening
- Fix the known issue: config.py currently defaults to a publicly known webhook secret
  ("test_webhook_secret"). In production (APP_ENVIRONMENT=production) the app must refuse
  to boot if this default is still in use — mirror the existing fail-loud pattern already
  used for JWT_SECRET_KEY
- Add webhook replay protection: reject deliveries outside a reasonable timestamp window,
  and confirm the existing (payment_id, attempt_id) idempotency also prevents a replayed
  valid payload from re-triggering an action. Verify this with the existing simulated
  payloads first — the real-payload check happens in Block 3
- Review what customer/payment data appears in logs and the audit trail; mask or redact
  anything unnecessarily sensitive, and document the current data-retention stance even if
  full enforcement is future work
- Improve observability incrementally on top of what exists (structured logging where it's
  missing, better error context) — don't introduce a new monitoring stack unless you can
  justify why the existing operational-metrics/PSI setup genuinely can't cover the gap
- Fix the outstanding scikit-learn version-mismatch warning when loading the model in
  Docker — pin the dependency or retrain inside the container's exact environment, your
  call, but document which and why
- Commit and push once this block's tests are green

## Block 3 — Wire in real Razorpay test-mode
- Read credentials from .env only — never ask me to paste one into chat, never hardcode one
- Verify the now-hardened webhook signature path against a REAL Razorpay payload delivered
  through the configured tunnel, not just simulated payloads. This is the real proof the
  Block 2 hardening actually works end to end
- If RAZORPAY_KEY_SECRET is present specifically for submitting real retries, wire
  actions.py to call the real Razorpay API instead of the injected simulated provider for
  that path. If it's absent, keep using the simulated provider even with webhook
  verification now real — keep these two things separable
- The real API call must sit strictly behind the existing decision engine, not as a new
  entry point that can trigger an action on its own. Add a test proving a
  FRAUD_RISK_DECLINE case never results in an actual outbound call to Razorpay, even with
  real credentials configured
- Document in docs/phase-notes/ exactly how you manually verified the real webhook —
  what you sent, what arrived, what happened. "Configured it" is not the same claim as
  "watched a real webhook get processed correctly"
- Commit and push once verified

## Block 4 — Wire in real Gemini (GEMINI_API_KEY)
- Add the google-genai SDK to pyproject.toml
- Keep the exact same bounded shape that already exists, just swap the implementation:
  - CommunicationGenerator: receives an ALREADY-APPROVED action and writes prose only. It
    must remain structurally impossible for this call to influence, choose, or override the
    action — it only ever sees one already-decided action, never a set of candidates
  - RevenueAnalyst: can only answer using the four existing read-only tools
    (get_recovery_metrics, get_failure_breakdown, get_gateway_health,
    get_top_priority_cases), and every number in its answer must be traceable to a specific
    tool call made in that turn. If it can't back a number with a tool call, it says it
    doesn't know rather than stating a figure
- Add a graceful fallback: if the Gemini call fails, times out, or the key is invalid, fall
  back to the existing deterministic template/keyword-routing behavior rather than erroring
  out. The system must keep working with zero external dependencies if Gemini is ever
  unavailable, exactly like it does today
- Add boundary tests specifically because a real model is more likely to try to be
  "helpful" around a constraint than the old fixed template was:
  - A leading/adversarial analyst question still can't produce a number without a backing
    tool call
  - The communication generator can't be steered into implying a different action than the
    one actually approved
  - The fallback path actually activates when the API call fails
- Keep a config flag for fully deterministic mode (no external calls at all) — Gemini
  becomes the new default when the key is present, but the old path must still work
- Commit and push once these tests are green

## Block 5 — Phase 15: scale-readiness
- Assess whether the current architecture (SQLite/Postgres + the Phase 10 task queue/
  worker) has a concrete bottleneck worth addressing, given this project's real usage
  pattern (demo/test-mode scale, not live production traffic)
- Only propose and build changes you can justify against an actual, stated need — don't add
  Kafka, Kubernetes, or horizontal scaling by default just because "scale-readiness" sounds
  like it should include them
- Write your reasoning in docs/phase-notes/phase-15.md regardless of whether you conclude
  "nothing more needed right now" or make a specific change — both are valid outcomes
- Commit and push

## Working agreement (unchanged)
- If anything is ambiguous, security-relevant, or a real product/business decision, ask me
  directly rather than guessing or defaulting
- Never weaken or delete an existing passing test to make new work pass
- Never log, print, or commit an actual secret value; confirm .env stays gitignored and
  .env.example stays placeholder-only
- Preserve every existing safety invariant without exception: fraud hard stop has no
  override path at any role, every action still routes through the same decision engine,
  guardrails still sit between scoring and execution no matter what triggers them —
  including the two new real-integration entry points added in Blocks 3 and 4

When all five blocks are complete and verified, give me the same honest status report as
always: what's actually running end-to-end now (and what you manually verified vs. only
unit-tested), and anything still open.