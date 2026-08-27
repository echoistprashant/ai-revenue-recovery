# Phase 5 — GenAI Layer

## Objective

Add useful language capabilities while making it structurally impossible for the language layer to select or execute a financial action.

## Implemented

- Immutable approved-communication input
- Customer message generation for all seven approved action types
- Read-only analyst tool registry
- Exactly four approved analytics tools
- Intent-based tool routing
- Grounded answers that identify their data source
- Honest tool-failure responses
- Typed communication and analyst API endpoints
- Offline deterministic implementation requiring no credentials

## LLM Boundary

The communication generator receives a `RecoveryAction` that has already been selected. Its output contains message text and echoes the immutable approved action; it cannot return a replacement action.

The analyst tool registry exposes only:

- `get_recovery_metrics`
- `get_failure_breakdown`
- `get_gateway_health`
- `get_top_priority_cases`

There is no retry, payment, amount-change, configuration, guardrail, or decision tool.

## Grounding

Analyst answers include the selected tool name and its returned project data. If a tool fails, the answer reports the limitation rather than inventing a value.

The implementation follows the structured tool-calling boundary described by official OpenAI documentation: <https://developers.openai.com/api/docs/guides/function-calling>.

## Provider Strategy

The current implementation is deterministic and offline so the full project remains runnable without an API key. A future provider adapter may replace prose generation, but it must preserve the same restricted inputs and tool registry.

## Verification

Tests prove that:

- a fraud stop message cannot become a retry message
- the exact analyst tool set is read-only
- an `execute_retry` tool is rejected
- answers contain actual tool results
- tool failures are disclosed
- API responses preserve the approved action

No external payment or LLM action is executed.
