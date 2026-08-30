# Block 4 Phase Notes — Bounded Gemini Integration & Fallback Infrastructure

## Objective
Integrate the official google-genai SDK for customer communication generation and natural language revenue analytics, while strictly enforcing non-negotiable architectural boundaries and deterministic fallbacks.

---

## Technical Implementation

1. **SDK & Dependencies (pyproject.toml):**
   - Added "google-genai>=1.0,<2" to core project dependencies.

2. **Configuration & Mode Control (config.py):**
   - Added gemini_api_key and deterministic_llm_mode settings loaded from GEMINI_API_KEY and LLM_MODE.
   - has_gemini_key property returns True iff gemini_api_key is present AND deterministic_llm_mode is False. Setting LLM_MODE=deterministic forces standard deterministic templates/routing without external API calls.

3. **LLM Boundary Integration (llm_boundary.py):**
   - **CommunicationGenerator**: Receives only an ALREADY-APPROVED single action (ApprovedCommunication). Uses Gemini gemini-2.5-flash with a strict system prompt instructing the model to generate customer prose only. It is structurally impossible for Gemini to select or alter the financial action. If the call fails or key is absent, falls back to static templates (TEMPLATES).
   - **RevenueAnalyst**: Binds Gemini tool/function calling strictly to the 4 approved read-only tools (get_recovery_metrics, get_failure_breakdown, get_gateway_health, get_top_priority_cases). System prompt enforces that every number must be directly backed by a tool call result. On failure or missing key, falls back to keyword-based deterministic tool routing.

---

## Safety Invariants & Verification

- **Invariant 1 (LLM is NOT the Decision Maker):** CommunicationGenerator never receives action candidates — only the single pre-approved action.
- **Invariant 2 (No Unbacked Numbers):** System instruction and function response validation enforce tool provenance.
- **Invariant 3 (Zero External Dependency Fallback):** The system operates fully deterministically without internet access or API credentials.
- **Automated Tests:** Added 	ests/test_gemini_boundary.py (6 tests passing). Total backend test suite: 306 passed tests.
