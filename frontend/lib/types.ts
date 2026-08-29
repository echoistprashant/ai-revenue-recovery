/**
 * Response and request shapes for the FastAPI backend.
 *
 * These mirror `src/revenue_recovery/models.py`. They are hand-written rather than
 * generated because the surface is small and a generator would be one more build step
 * to keep honest; when the Pydantic models change, these change with them.
 */

export type Role = "VIEWER" | "OPERATOR" | "ADMIN";

export type FailureCategory =
  | "INSUFFICIENT_FUNDS"
  | "EXPIRED_CARD"
  | "INVALID_CARD"
  | "AUTHENTICATION_FAILURE"
  | "BANK_DECLINED"
  | "GATEWAY_OR_NETWORK_FAILURE"
  | "FRAUD_RISK_DECLINE"
  | "PAYMENT_METHOD_FAILURE"
  | "TEMPORARY_BANK_ISSUE";

export const FAILURE_CATEGORIES: readonly FailureCategory[] = [
  "INSUFFICIENT_FUNDS",
  "EXPIRED_CARD",
  "INVALID_CARD",
  "AUTHENTICATION_FAILURE",
  "BANK_DECLINED",
  "GATEWAY_OR_NETWORK_FAILURE",
  "FRAUD_RISK_DECLINE",
  "PAYMENT_METHOD_FAILURE",
  "TEMPORARY_BANK_ISSUE",
];

export type PaymentMethod = "CARD" | "UPI" | "NET_BANKING" | "WALLET";

export const PAYMENT_METHODS: readonly PaymentMethod[] = ["CARD", "UPI", "NET_BANKING", "WALLET"];

export type RecoveryAction =
  | "RETRY_NOW"
  | "RETRY_LATER"
  | "CHANGE_PAYMENT_METHOD"
  | "SEND_NOTIFICATION"
  | "SUPPRESS_RETRY"
  | "ESCALATE_TO_HUMAN"
  | "STOP_RECOVERY";

export const RECOVERY_ACTIONS: readonly RecoveryAction[] = [
  "RETRY_NOW",
  "RETRY_LATER",
  "CHANGE_PAYMENT_METHOD",
  "SEND_NOTIFICATION",
  "SUPPRESS_RETRY",
  "ESCALATE_TO_HUMAN",
  "STOP_RECOVERY",
];

/**
 * Actions that mean no recovery attempt was made.
 *
 * There is no `NO_ACTION` value in the backend: when a guardrail refuses, the engine
 * returns the forced action itself — the retry is suppressed, stopped, or handed to a
 * person (see `DecisionEngine.decide` and `evaluate_guardrails`). Keeping the list here
 * rather than inline in a component means both ingestion surfaces agree on what
 * "withheld" means, and the rule can be tested without rendering anything.
 */
export const WITHHELD_ACTIONS: readonly RecoveryAction[] = [
  "SUPPRESS_RETRY",
  "ESCALATE_TO_HUMAN",
  "STOP_RECOVERY",
];

/** True when the pipeline deliberately did not attempt recovery. */
export function isWithheld(action: RecoveryAction): boolean {
  return WITHHELD_ACTIONS.includes(action);
}

export type CaseResolution = "MANUAL_RECOVERED" | "WRITTEN_OFF" | "MANUAL_RETRY";

export interface UserResponse {
  user_id: number;
  username: string;
  role: Role;
  tenant_id: string;
  is_active: boolean;
  created_at: string;
  last_login_at?: string | null;
}

export interface RecoveryMetrics {
  total_failures: number;
  resolved_events: number;
  recovered_events: number;
  unresolved_events: number;
  recovery_rate: number;
  recovered_revenue: number;
  failure_breakdown: Record<string, number>;
}

export interface PriorityCase {
  payment_id: string;
  attempt_id: string;
  failure_category: FailureCategory;
  amount: number;
  recovery_probability: number;
  churn_risk: number;
  revenue_at_risk: number;
  priority_score: number;
  model_version: string;
}

export interface EventHistoryItem {
  event_id: number;
  payment_id: string;
  attempt_id: string;
  customer_id: string;
  amount: number;
  currency: string;
  payment_method: string;
  gateway: string;
  bank: string;
  failure_category: FailureCategory;
  event_timestamp: string;
  action: RecoveryAction;
  reason: string;
  final_state: string;
  recovered?: boolean | null;
  recovery_probability?: number | null;
  churn_risk?: number | null;
  revenue_at_risk?: number | null;
  priority_score?: number | null;
  created_at: string;
}

export interface AuditEntry {
  audit_id: number;
  event_id: number;
  event_type: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ReviewCase {
  event_id: number;
  payment_id: string;
  attempt_id: string;
  customer_id: string;
  amount: number;
  currency: string;
  failure_category: FailureCategory;
  action: RecoveryAction;
  reason: string;
  final_state: string;
  recovery_probability?: number | null;
  churn_risk?: number | null;
  revenue_at_risk?: number | null;
  priority_score?: number | null;
  created_at: string;
}

export interface ResolveCaseResponse {
  event_id: number;
  resolution: CaseResolution;
  final_state: string;
  recovered: boolean | null;
  executed: boolean;
  detail: string;
  resolved_by: string;
  resolved_at: string;
}

export interface ProcessedEvent {
  event_id: number;
  payment_id: string;
  attempt_id: string;
  failure_category: FailureCategory;
  action: RecoveryAction;
  retry_delay_hours: number | null;
  reason: string;
  recovered: boolean | null;
  recovery_probability?: number | null;
  churn_risk?: number | null;
  revenue_at_risk?: number | null;
  priority_score?: number | null;
  model_version?: string | null;
  duplicate: boolean;
}

export interface DecisionResponse {
  action: string;
  reason: string;
  guardrail_rule: string | null;
  guardrail_reason: string;
}

export interface OptimizationResponse {
  customer_id: string;
  retry_after_hours: number;
  preferred_hour: number;
  timing_confidence: number;
  timing_reason: string;
  recommended_payment_method: PaymentMethod;
  method_success_rate: number;
  method_sample_size: number;
  method_confidence: number;
  method_reason: string;
}

export interface GatewayHealthResponse {
  bank: string;
  gateway: string;
  baseline_failure_rate: number;
  observed_failure_rate: number;
  failure_multiplier: number;
  incident_active: boolean;
}

export interface CommunicationResponse {
  message: string;
  action: RecoveryAction;
}

export interface AnalystResponse {
  answer: string;
}

export interface VariantMetrics {
  variant: string;
  sample_size: number;
  recovered_count: number;
  recovery_rate: number;
  recovered_revenue: number;
  unresolved_count: number;
}

export interface ExperimentResponse {
  experiment_id: string;
  control: VariantMetrics;
  treatment: VariantMetrics;
  recovery_rate_delta: number;
  recovered_revenue_delta: number;
  confidence_interval_95: [number, number];
  statistically_distinguishable: boolean;
}

export interface DriftResponse {
  psi: number;
  status: string;
}

/** `/operational-metrics` returns a flat map rather than a fixed model. */
export type OperationalMetrics = Record<string, number | string>;

/** `/tasks/stats` likewise. */
export type TaskStats = Record<string, number | string>;
