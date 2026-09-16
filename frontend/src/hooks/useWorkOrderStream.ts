import { useEffect, useState } from "react";

import { streamUrl } from "../api/client";
import {
  emptyAnomalyDetails,
  emptyDraftWorkOrder,
  type AnomalyClassification,
  type AnomalyDetails,
  type DraftWorkOrder,
  type GraphNodeName,
  type InterruptPayload,
  type RetrievedContextItem,
  type TraceEventOut,
  type WorkOrderStatus,
} from "../api/types";

export interface WorkOrderStreamState {
  status: WorkOrderStatus | "connecting";
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  anomalyClassification: AnomalyClassification;
  anomalyDetails: AnomalyDetails;
  retrievedContext: RetrievedContextItem[];
  rootCauseHypothesis: string;
  recommendedResponse: string;
  citations: string[];
  draftWorkOrder: DraftWorkOrder;
  trace: TraceEventOut[];
  interrupt: InterruptPayload | null;
  finalStatus: string | null;
  error: string | null;
}

const INITIAL_STATE: WorkOrderStreamState = {
  status: "connecting",
  currentNode: null,
  completedNodes: [],
  anomalyClassification: "",
  anomalyDetails: emptyAnomalyDetails(),
  retrievedContext: [],
  rootCauseHypothesis: "",
  recommendedResponse: "",
  citations: [],
  draftWorkOrder: emptyDraftWorkOrder(),
  trace: [],
  interrupt: null,
  finalStatus: null,
  error: null,
};

const TERMINAL_STATUSES = new Set(["work_order_approved", "escalated", "dismissed_benign", "normal_logged", "error"]);

/**
 * Subscribes to `GET /work-orders/{id}/stream` (Server-Sent Events) and
 * folds the incoming events into a single state object a component can
 * render directly -- driving both the live GraphView highlighting and the
 * anomaly/investigation/draft-work-order output panels.
 */
export function useWorkOrderStream(workOrderId: string | null, generation = 0): WorkOrderStreamState {
  const [state, setState] = useState<WorkOrderStreamState>(INITIAL_STATE);

  useEffect(() => {
    if (!workOrderId) {
      setState(INITIAL_STATE);
      return;
    }

    setState({ ...INITIAL_STATE, status: "connecting" });
    const source = new EventSource(streamUrl(workOrderId));

    source.addEventListener("node", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        node: GraphNodeName;
        output: Record<string, unknown>;
        trace: TraceEventOut[];
      };
      setState((prev) => ({
        ...prev,
        status: "running",
        currentNode: data.node,
        completedNodes: prev.completedNodes.includes(data.node)
          ? prev.completedNodes
          : [...prev.completedNodes, data.node],
        anomalyClassification:
          (data.output.anomaly_classification as AnomalyClassification | undefined) ?? prev.anomalyClassification,
        anomalyDetails: (data.output.anomaly_details as AnomalyDetails | undefined) ?? prev.anomalyDetails,
        retrievedContext: (data.output.retrieved_context as RetrievedContextItem[] | undefined) ?? prev.retrievedContext,
        rootCauseHypothesis: (data.output.root_cause_hypothesis as string | undefined) ?? prev.rootCauseHypothesis,
        recommendedResponse: (data.output.recommended_response as string | undefined) ?? prev.recommendedResponse,
        citations: (data.output.citations as string[] | undefined) ?? prev.citations,
        draftWorkOrder: (data.output.draft_work_order as DraftWorkOrder | undefined) ?? prev.draftWorkOrder,
        trace: [...prev.trace, ...data.trace],
      }));
    });

    source.addEventListener("interrupt", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as InterruptPayload;
      setState((prev) => ({
        ...prev,
        status: "awaiting_engineer_review",
        currentNode: "engineer_review",
        completedNodes: prev.completedNodes.includes("engineer_review")
          ? prev.completedNodes
          : [...prev.completedNodes, "engineer_review"],
        anomalyClassification: data.anomaly_classification ?? prev.anomalyClassification,
        anomalyDetails: data.anomaly_details ?? prev.anomalyDetails,
        retrievedContext: data.retrieved_context ?? prev.retrievedContext,
        rootCauseHypothesis: data.root_cause_hypothesis ?? prev.rootCauseHypothesis,
        recommendedResponse: data.recommended_response ?? prev.recommendedResponse,
        citations: data.citations ?? prev.citations,
        draftWorkOrder: data.draft_work_order ?? prev.draftWorkOrder,
        interrupt: data,
      }));
    });

    source.addEventListener("done", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: WorkOrderStatus;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        finalStatus: data.final_status,
        currentNode: TERMINAL_STATUSES.has(data.status)
          ? data.status === "normal_logged"
            ? "log_normal"
            : "finalize"
          : prev.currentNode,
        completedNodes: (() => {
          if (!TERMINAL_STATUSES.has(data.status)) return prev.completedNodes;
          const terminalNode = data.status === "normal_logged" ? "log_normal" : "finalize";
          return prev.completedNodes.includes(terminalNode) ? prev.completedNodes : [...prev.completedNodes, terminalNode];
        })(),
      }));
      source.close();
    });

    source.addEventListener("replay", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: WorkOrderStatus;
        trace: TraceEventOut[];
        state_snapshot: Record<string, unknown>;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        trace: data.trace,
        anomalyClassification:
          (data.state_snapshot.anomaly_classification as AnomalyClassification | undefined) ?? prev.anomalyClassification,
        anomalyDetails: (data.state_snapshot.anomaly_details as AnomalyDetails | undefined) ?? prev.anomalyDetails,
        retrievedContext:
          (data.state_snapshot.retrieved_context as RetrievedContextItem[] | undefined) ?? prev.retrievedContext,
        rootCauseHypothesis:
          (data.state_snapshot.root_cause_hypothesis as string | undefined) ?? prev.rootCauseHypothesis,
        recommendedResponse:
          (data.state_snapshot.recommended_response as string | undefined) ?? prev.recommendedResponse,
        citations: (data.state_snapshot.citations as string[] | undefined) ?? prev.citations,
        draftWorkOrder: (data.state_snapshot.draft_work_order as DraftWorkOrder | undefined) ?? prev.draftWorkOrder,
        finalStatus: data.final_status,
      }));
    });

    source.addEventListener("error", (evt) => {
      // Only MessageEvents carry a backend-emitted `error` payload; a plain
      // connection failure fires this same listener with no `.data`.
      const data = (evt as MessageEvent).data;
      if (typeof data === "string") {
        const parsed = JSON.parse(data) as { message: string };
        setState((prev) => ({ ...prev, status: "error", error: parsed.message }));
        source.close();
      }
    });

    source.onerror = () => {
      setState((prev) =>
        TERMINAL_STATUSES.has(prev.status)
          ? prev
          : { ...prev, error: prev.error ?? "Connection to the work order stream was lost." },
      );
    };

    return () => {
      source.close();
    };
    // `generation` is bumped by callers (e.g. after POST /resume) to force
    // a fresh EventSource connection against the new background task.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workOrderId, generation]);

  return state;
}
