/**
 * Hand-written TypeScript mirror of `backend/app/api/schemas.py`.
 * Keep these two files in sync when the API contract changes.
 */

export type WorkOrderStatus =
  | "pending"
  | "running"
  | "awaiting_engineer_review"
  | "work_order_approved"
  | "escalated"
  | "dismissed_benign"
  | "normal_logged"
  | "error";

export type HumanDecision = "approve" | "escalate" | "dismiss_benign";

export type AnomalyClassification = "normal" | "warning" | "critical" | "";

export interface SensorTagSummary {
  tag_id: string;
  name: string;
  unit: string;
  equipment_id: string;
  equipment_name: string;
  normal_min: number;
  normal_max: number;
  critical_min: number;
  critical_max: number;
  current_status: string;
  last_evaluated_at: string | null;
  last_work_order_id: string | null;
}

export interface SensorTagDetail extends SensorTagSummary {
  description: string;
  warning_z: number;
  warning_rate_per_hour: number;
}

export interface SensorTagListResponse {
  tags: SensorTagSummary[];
}

export interface ReadingPoint {
  timestamp: string;
  value: number;
}

export interface ReadingsResponse {
  tag_id: string;
  readings: ReadingPoint[];
}

export interface SampleAnomaly {
  id: string;
  label: string;
  tag_id: string;
  timestamp: string;
  expected_classification: string;
}

export interface SamplesResponse {
  samples: SampleAnomaly[];
}

export interface WorkOrderCreateResponse {
  id: string;
  tag_id: string;
  status: WorkOrderStatus;
}

export interface AnomalyDetails {
  rolling_mean: number | null;
  rolling_std: number | null;
  z_score: number | null;
  rate_per_hour: number | null;
  stuck_detected: boolean;
  threshold_breach: string;
  history_window_size: number;
  reasons: string[];
}

export function emptyAnomalyDetails(): AnomalyDetails {
  return {
    rolling_mean: null,
    rolling_std: null,
    z_score: null,
    rate_per_hour: null,
    stuck_detected: false,
    threshold_breach: "none",
    history_window_size: 0,
    reasons: [],
  };
}

export interface RetrievedContextItem {
  chunk_id: string;
  doc_type: "manual" | "incident" | string;
  title: string;
  equipment_id: string;
  equipment_name: string;
  text: string;
  score: number;
}

export interface DraftWorkOrder {
  tag_id: string;
  tag_name: string;
  equipment_id: string;
  equipment_name: string;
  observed_anomaly: string;
  severity: string;
  title: string;
  description: string;
  recommended_action: string;
  priority: "low" | "medium" | "high" | "urgent" | string;
}

export function emptyDraftWorkOrder(): DraftWorkOrder {
  return {
    tag_id: "",
    tag_name: "",
    equipment_id: "",
    equipment_name: "",
    observed_anomaly: "",
    severity: "",
    title: "",
    description: "",
    recommended_action: "",
    priority: "medium",
  };
}

export interface HumanDecisionRequest {
  decision: HumanDecision;
  feedback: string;
  corrected_draft_work_order?: DraftWorkOrder | null;
}

export interface TraceEventOut {
  node: string;
  timestamp: string;
  summary: string;
}

export interface WorkOrderSummary {
  id: string;
  tag_id: string;
  equipment_id: string;
  equipment_name: string;
  reading_timestamp: string;
  reading_value: number;
  status: WorkOrderStatus;
  final_status: string | null;
  anomaly_classification: string;
  created_at: string;
  updated_at: string;
}

export interface WorkOrderDetail extends WorkOrderSummary {
  anomaly_details: AnomalyDetails;
  retrieved_context: RetrievedContextItem[];
  root_cause_hypothesis: string;
  recommended_response: string;
  citations: string[];
  draft_work_order: DraftWorkOrder;
  human_decision: string | null;
  human_feedback: string;
  trace: TraceEventOut[];
  state_snapshot: Record<string, unknown>;
  error: string | null;
}

export interface WorkOrderListResponse {
  work_orders: WorkOrderSummary[];
}

/** Payload of the `interrupt` SSE event -- what `engineer_review_node` pauses with. */
export interface InterruptPayload {
  tag_meta: Record<string, unknown>;
  reading_value: number;
  reading_timestamp: string;
  anomaly_classification: AnomalyClassification;
  anomaly_details: AnomalyDetails;
  retrieved_context: RetrievedContextItem[];
  root_cause_hypothesis: string;
  recommended_response: string;
  citations: string[];
  draft_work_order: DraftWorkOrder;
}

/** Shapes of the SSE events emitted by GET /work-orders/{id}/stream. */
export type StreamEvent =
  | { type: "node"; node: string; output: Record<string, unknown>; trace: TraceEventOut[] }
  | { type: "interrupt"; data: InterruptPayload }
  | { type: "done"; status: WorkOrderStatus; final_status: string | null }
  | { type: "error"; message: string }
  | {
      type: "replay";
      status: WorkOrderStatus;
      trace: TraceEventOut[];
      state_snapshot: Record<string, unknown>;
      final_status: string | null;
    };

/** The graph node names, in the order they appear in the LangGraph
 * StateGraph (backend/app/graph/graph.py). Unlike earlier tutorials in this
 * series, this graph has real conditional routing: `detect_anomaly` routes
 * to EITHER `log_normal` (most readings) OR the investigate/draft/review
 * branch (warning/critical readings only) -- never both. */
export const GRAPH_NODES = [
  "ingest_reading",
  "detect_anomaly",
  "log_normal",
  "investigate",
  "draft_work_order",
  "engineer_review",
  "finalize",
] as const;

export type GraphNodeName = (typeof GRAPH_NODES)[number];

export const GRAPH_NODE_LABELS: Record<GraphNodeName, string> = {
  ingest_reading: "Ingest Reading",
  detect_anomaly: "Detect Anomaly",
  log_normal: "Log Normal",
  investigate: "Investigate",
  draft_work_order: "Draft Work Order",
  engineer_review: "Engineer Review",
  finalize: "Finalize",
};

export const STATUS_LABELS: Record<WorkOrderStatus, string> = {
  pending: "Pending",
  running: "Running",
  awaiting_engineer_review: "Awaiting engineer review",
  work_order_approved: "Work order approved",
  escalated: "Escalated",
  dismissed_benign: "Dismissed as benign",
  normal_logged: "Normal (logged)",
  error: "Error",
};

export const TAG_STATUS_LABELS: Record<string, string> = {
  unknown: "Unknown",
  normal: "Normal",
  warning: "Warning",
  critical: "Critical",
};
