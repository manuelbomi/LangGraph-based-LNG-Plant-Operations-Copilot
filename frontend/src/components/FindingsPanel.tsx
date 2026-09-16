import type { AnomalyClassification, AnomalyDetails, DraftWorkOrder, RetrievedContextItem, TraceEventOut } from "../api/types";
import { TagStatusBadge } from "./StatusBadge";

interface FindingsPanelProps {
  anomalyClassification: AnomalyClassification;
  anomalyDetails: AnomalyDetails;
  retrievedContext: RetrievedContextItem[];
  rootCauseHypothesis: string;
  recommendedResponse: string;
  draftWorkOrder: DraftWorkOrder;
  trace: TraceEventOut[];
}

/** Live/replayed intermediate output from the graph run: anomaly
 * classification + statistical reasons, retrieved manual/incident context,
 * root-cause hypothesis, draft work order, and the node trace log. */
export function FindingsPanel({
  anomalyClassification,
  anomalyDetails,
  retrievedContext,
  rootCauseHypothesis,
  recommendedResponse,
  draftWorkOrder,
  trace,
}: FindingsPanelProps) {
  return (
    <div className="h-[620px] space-y-3 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
      {anomalyClassification && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Anomaly classification</h4>
          <div className="flex items-center gap-2">
            <TagStatusBadge status={anomalyClassification} />
            {anomalyDetails.stuck_detected && (
              <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
                sensor may be stuck
              </span>
            )}
          </div>
          {anomalyDetails.reasons.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-slate-600">
              {anomalyDetails.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {retrievedContext.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">
            Retrieved manual/incident context ({retrievedContext.length})
          </h4>
          <ul className="space-y-2">
            {retrievedContext.map((c) => (
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

      {rootCauseHypothesis && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Root-cause hypothesis</h4>
          <p className="text-sm text-slate-700">{rootCauseHypothesis}</p>
        </div>
      )}

      {recommendedResponse && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Recommended response</h4>
          <p className="text-sm text-slate-700">{recommendedResponse}</p>
        </div>
      )}

      {draftWorkOrder.title && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Draft work order</h4>
          <p className="text-sm font-medium text-slate-800">{draftWorkOrder.title}</p>
          <p className="mt-1 text-xs text-slate-600">Priority: {draftWorkOrder.priority}</p>
          <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">{draftWorkOrder.description}</p>
        </div>
      )}

      {trace.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Trace</h4>
          <ul className="space-y-1 text-xs text-slate-500">
            {trace.map((event, i) => (
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
