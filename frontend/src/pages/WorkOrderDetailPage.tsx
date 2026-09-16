import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getTag, getTagReadings, getWorkOrder, resumeWorkOrder } from "../api/client";
import type { HumanDecisionRequest, InterruptPayload } from "../api/types";
import { SensorChart } from "../components/SensorChart";
import { ReviewForm } from "../components/ReviewForm";
import { StatusBadge, TagStatusBadge } from "../components/StatusBadge";

const IN_PROGRESS_STATUSES = new Set(["pending", "running"]);

const FINAL_STATUS_LABEL: Record<string, string> = {
  work_order_approved: "Work order approved",
  escalated: "Escalated",
  dismissed_benign: "Dismissed as benign",
  normal: "Normal",
};

/** The work order detail / "example analysis" view: the anomaly chart
 * (centered on the triggering reading), investigation findings, the
 * (possibly engineer-corrected) work order, the node trace, and -- if this
 * event is still awaiting engineer review -- the review panel itself,
 * reachable directly from the queue without needing a live SSE connection. */
export function WorkOrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["work-order", id],
    queryFn: () => getWorkOrder(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data && IN_PROGRESS_STATUSES.has(query.state.data.status) ? 1000 : false),
  });

  const { data: tag } = useQuery({
    queryKey: ["tag", data?.tag_id],
    queryFn: () => getTag(data!.tag_id),
    enabled: Boolean(data?.tag_id),
  });

  const { data: readingsData } = useQuery({
    queryKey: ["readings", data?.tag_id, data?.reading_timestamp],
    queryFn: () => getTagReadings(data!.tag_id, { hours: 336, end: data!.reading_timestamp }),
    enabled: Boolean(data?.tag_id && data?.reading_timestamp),
  });

  const resumeMutation = useMutation({
    mutationFn: (payload: HumanDecisionRequest) => resumeWorkOrder(id as string, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["work-order", id] });
      queryClient.invalidateQueries({ queryKey: ["work-orders"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  if (isLoading) {
    return <p className="text-sm text-slate-400">Loading work order...</p>;
  }
  if (error || !data) {
    return <p className="text-sm text-rose-600">Could not load this work order.</p>;
  }

  const interruptPayload: InterruptPayload = {
    tag_meta: {},
    reading_value: data.reading_value,
    reading_timestamp: data.reading_timestamp,
    anomaly_classification: (data.anomaly_classification || "warning") as InterruptPayload["anomaly_classification"],
    anomaly_details: data.anomaly_details,
    retrieved_context: data.retrieved_context,
    root_cause_hypothesis: data.root_cause_hypothesis,
    recommended_response: data.recommended_response,
    citations: data.citations,
    draft_work_order: data.draft_work_order,
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <Link to="/work-orders" className="text-xs text-brand-700 hover:underline">
          &larr; Back to Work Order Queue
        </Link>
        <h2 className="mt-1 text-xl font-semibold text-slate-900">
          {data.draft_work_order.title || `${data.equipment_name} anomaly`}
        </h2>
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <StatusBadge status={data.status} />
          {data.anomaly_classification && <TagStatusBadge status={data.anomaly_classification} />}
          {data.final_status && <span>&middot; {FINAL_STATUS_LABEL[data.final_status] ?? data.final_status}</span>}
          <span>
            &middot;{" "}
            <Link to={`/tags/${encodeURIComponent(data.tag_id)}`} className="text-brand-700 hover:underline">
              {data.equipment_name} ({data.tag_id})
            </Link>
          </span>
        </p>
      </div>

      {data.error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{data.error}</p>}

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
          Reading of {data.reading_value} {tag?.unit ?? ""} at {new Date(data.reading_timestamp).toUTCString()}
        </h4>
        {readingsData && tag ? (
          <SensorChart
            readings={readingsData.readings}
            unit={tag.unit}
            normalMin={tag.normal_min}
            normalMax={tag.normal_max}
            criticalMin={tag.critical_min}
            criticalMax={tag.critical_max}
            highlight={{
              timestamp: data.reading_timestamp,
              value: data.reading_value,
              classification: data.anomaly_classification,
            }}
          />
        ) : (
          <p className="text-sm text-slate-400">Loading chart...</p>
        )}
      </div>

      {data.status === "awaiting_engineer_review" ? (
        <ReviewForm
          interrupt={interruptPayload}
          submitting={resumeMutation.isPending}
          onDecision={(decision) => resumeMutation.mutate(decision)}
        />
      ) : (
        <>
          {data.anomaly_details.reasons?.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Anomaly detection reasons</h4>
              <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                {data.anomaly_details.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {data.retrieved_context.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                Retrieved manual/incident context
              </h4>
              <ul className="space-y-2">
                {data.retrieved_context.map((c) => (
                  <li key={c.chunk_id} className="rounded border border-slate-100 bg-slate-50 p-2 text-xs">
                    <span className="font-medium text-slate-700">
                      [{c.doc_type === "manual" ? "Manual" : "Incident"}: {c.title}]
                    </span>
                    <p className="mt-1 text-slate-600">{c.text}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.root_cause_hypothesis && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Root-cause hypothesis</h4>
              <p className="text-slate-700">{data.root_cause_hypothesis}</p>
            </div>
          )}

          {data.draft_work_order.title && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                {data.final_status ? "Final work order" : "Draft work order"}
              </h4>
              <p className="font-medium text-slate-800">{data.draft_work_order.title}</p>
              <p className="mt-1 text-xs text-slate-500">Priority: {data.draft_work_order.priority}</p>
              <p className="mt-2 whitespace-pre-wrap text-slate-700">{data.draft_work_order.description}</p>
            </div>
          )}

          {data.human_decision && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Engineer decision</h4>
              <p className="text-slate-700">
                <span className="font-medium">{data.human_decision}</span>
                {data.human_feedback && <> -- {data.human_feedback}</>}
              </p>
            </div>
          )}
        </>
      )}

      {data.trace.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Trace</h4>
          <ul className="space-y-1 text-xs text-slate-500">
            {data.trace.map((event, i) => (
              <li key={i}>
                <span className="font-mono text-slate-400">{event.node}</span> -- {event.summary}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
