import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { listSamples, listTags, resumeWorkOrder, runSampleAnomaly } from "../api/client";
import type { HumanDecisionRequest } from "../api/types";
import { FindingsPanel } from "../components/FindingsPanel";
import { GraphView } from "../components/GraphView";
import { ReviewForm } from "../components/ReviewForm";
import { TagStatusBadge } from "../components/StatusBadge";
import { useWorkOrderStream } from "../hooks/useWorkOrderStream";

const TERMINAL_STATUSES = new Set(["work_order_approved", "escalated", "dismissed_benign", "normal_logged", "error"]);

const FINAL_STATUS_LABEL: Record<string, string> = {
  work_order_approved: "Work order approved",
  escalated: "Escalated",
  dismissed_benign: "Dismissed as benign",
  normal: "Normal",
};

export function PlantDashboardPage() {
  const [selectedSample, setSelectedSample] = useState("");
  const [workOrderId, setWorkOrderId] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const queryClient = useQueryClient();

  const { data: tagsData, isLoading: tagsLoading } = useQuery({ queryKey: ["tags"], queryFn: listTags });
  const { data: samplesData } = useQuery({ queryKey: ["samples"], queryFn: listSamples });

  const sampleMutation = useMutation({
    mutationFn: (sampleId: string) => runSampleAnomaly(sampleId),
    onSuccess: (data) => {
      setWorkOrderId(data.id);
      setGeneration(0);
    },
  });

  const stream = useWorkOrderStream(workOrderId, generation);

  const resumeMutation = useMutation({
    mutationFn: (payload: HumanDecisionRequest) => resumeWorkOrder(workOrderId as string, payload),
    onSuccess: () => {
      setGeneration((g) => g + 1);
      queryClient.invalidateQueries({ queryKey: ["work-orders"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  const isRunActive = workOrderId !== null;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">Plant Dashboard</h2>
        <p className="mb-4 text-sm text-slate-500">
          Monitored equipment/tags at Northgate Point LNG Terminal (fictitious demo facility). Trigger processing
          of a bundled sample reading below to watch the graph classify it and, if abnormal, investigate and draft
          a work order for engineer review -- nothing here controls any equipment.
        </p>

        {tagsLoading ? (
          <p className="text-sm text-slate-400">Loading tags...</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {tagsData?.tags.map((tag) => (
              <Link
                key={tag.tag_id}
                to={`/tags/${encodeURIComponent(tag.tag_id)}`}
                className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand-300 hover:shadow"
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-400">{tag.tag_id}</span>
                  <TagStatusBadge status={tag.current_status} />
                </div>
                <div className="text-sm font-medium text-slate-800">{tag.name}</div>
                <div className="text-xs text-slate-500">{tag.equipment_name}</div>
                <div className="mt-2 text-xs text-slate-400">
                  Normal range: {tag.normal_min}-{tag.normal_max}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="mb-1 text-sm font-semibold text-slate-800">Trigger a sample reading</h3>
        <p className="mb-3 text-xs text-slate-500">
          Zero-setup demo readings bundled with this repo (see <code>sample-data/README.md</code>), including each
          injected drift/spike/stuck-sensor anomaly plus a healthy control reading.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <select
            value={selectedSample}
            onChange={(e) => setSelectedSample(e.target.value)}
            aria-label="Choose a sample reading"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Choose a sample reading...</option>
            {samplesData?.samples.map((sample) => (
              <option key={sample.id} value={sample.id}>
                {sample.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!selectedSample || sampleMutation.isPending}
            onClick={() => sampleMutation.mutate(selectedSample)}
            className="rounded-md bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
          >
            {sampleMutation.isPending ? "Starting..." : "Process reading"}
          </button>
        </div>
        {sampleMutation.isError && <p className="mt-2 text-sm text-rose-600">{(sampleMutation.error as Error).message}</p>}
      </div>

      {isRunActive && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-900">Live run</h3>
            <p className="text-sm text-slate-500">
              Status:{" "}
              <span className="font-medium text-slate-700">
                {stream.status === "connecting" ? "connecting..." : stream.status.replace(/_/g, " ")}
              </span>
              {stream.finalStatus && (
                <span className="ml-2 text-slate-500">&middot; {FINAL_STATUS_LABEL[stream.finalStatus] ?? stream.finalStatus}</span>
              )}
            </p>
          </div>

          {stream.error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{stream.error}</p>}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <GraphView currentNode={stream.currentNode} completedNodes={stream.completedNodes} />
            <FindingsPanel
              anomalyClassification={stream.anomalyClassification}
              anomalyDetails={stream.anomalyDetails}
              retrievedContext={stream.retrievedContext}
              rootCauseHypothesis={stream.rootCauseHypothesis}
              recommendedResponse={stream.recommendedResponse}
              draftWorkOrder={stream.draftWorkOrder}
              trace={stream.trace}
            />
          </div>

          {stream.status === "awaiting_engineer_review" && stream.interrupt && (
            <ReviewForm
              interrupt={stream.interrupt}
              submitting={resumeMutation.isPending}
              onDecision={(decision) => resumeMutation.mutate(decision)}
            />
          )}

          {TERMINAL_STATUSES.has(stream.status) && workOrderId && (
            <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-600">
              Done.{" "}
              <Link to={`/work-orders/${workOrderId}`} className="font-medium text-brand-700 hover:underline">
                View this event in the Work Order Queue
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </div>
  );
}
