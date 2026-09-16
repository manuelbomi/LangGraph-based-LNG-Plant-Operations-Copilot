import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getTag, getTagReadings, getWorkOrder, listWorkOrders } from "../api/client";
import { SensorChart } from "../components/SensorChart";
import { StatusBadge, TagStatusBadge } from "../components/StatusBadge";

/** The sensor detail view: a time-series chart of recent history for this
 * tag (recharts), with the selected event's anomaly point highlighted, and
 * the investigation findings for that event alongside it. */
export function SensorDetailPage() {
  const { tagId } = useParams<{ tagId: string }>();
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState<string | null>(null);

  const { data: tag, isLoading: tagLoading, error: tagError } = useQuery({
    queryKey: ["tag", tagId],
    queryFn: () => getTag(tagId as string),
    enabled: Boolean(tagId),
  });

  const { data: workOrdersData } = useQuery({
    queryKey: ["work-orders", tagId],
    queryFn: () => listWorkOrders({ tagId: tagId as string }),
    enabled: Boolean(tagId),
  });

  useEffect(() => {
    if (!selectedWorkOrderId && workOrdersData && workOrdersData.work_orders.length > 0) {
      const firstNonNormal = workOrdersData.work_orders.find((w) => w.anomaly_classification !== "normal");
      setSelectedWorkOrderId((firstNonNormal ?? workOrdersData.work_orders[0]).id);
    }
  }, [workOrdersData, selectedWorkOrderId]);

  const { data: selectedWorkOrder } = useQuery({
    queryKey: ["work-order", selectedWorkOrderId],
    queryFn: () => getWorkOrder(selectedWorkOrderId as string),
    enabled: Boolean(selectedWorkOrderId),
  });

  const { data: readingsData } = useQuery({
    queryKey: ["readings", tagId, selectedWorkOrder?.reading_timestamp],
    queryFn: () =>
      getTagReadings(tagId as string, {
        hours: 336,
        end: selectedWorkOrder?.reading_timestamp,
      }),
    enabled: Boolean(tagId),
  });

  if (tagLoading) return <p className="text-sm text-slate-400">Loading sensor tag...</p>;
  if (tagError || !tag) return <p className="text-sm text-rose-600">Could not load this sensor tag.</p>;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <Link to="/" className="text-xs text-brand-700 hover:underline">
          &larr; Back to Plant Dashboard
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold text-slate-900">{tag.name}</h2>
          <TagStatusBadge status={tag.current_status} />
        </div>
        <p className="text-sm text-slate-500">
          {tag.equipment_name} ({tag.equipment_id}) &middot; <span className="font-mono">{tag.tag_id}</span> &middot;
          unit: {tag.unit}
        </p>
        <p className="mt-1 text-xs text-slate-400">{tag.description}</p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase text-slate-500">Recent history (14 days)</h4>
          <p className="text-xs text-slate-400">
            Normal: {tag.normal_min}-{tag.normal_max} {tag.unit} &middot; Critical beyond {tag.critical_min}/
            {tag.critical_max}
          </p>
        </div>
        {readingsData ? (
          <SensorChart
            readings={readingsData.readings}
            unit={tag.unit}
            normalMin={tag.normal_min}
            normalMax={tag.normal_max}
            criticalMin={tag.critical_min}
            criticalMax={tag.critical_max}
            highlight={
              selectedWorkOrder
                ? {
                    timestamp: selectedWorkOrder.reading_timestamp,
                    value: selectedWorkOrder.reading_value,
                    classification: selectedWorkOrder.anomaly_classification,
                  }
                : undefined
            }
          />
        ) : (
          <p className="text-sm text-slate-400">Loading chart...</p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Associated events</h4>
        {!workOrdersData || workOrdersData.work_orders.length === 0 ? (
          <p className="text-sm text-slate-400">No anomaly events processed for this tag yet.</p>
        ) : (
          <ul className="space-y-1">
            {workOrdersData.work_orders.map((wo) => (
              <li key={wo.id}>
                <button
                  type="button"
                  onClick={() => setSelectedWorkOrderId(wo.id)}
                  className={`flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50 ${
                    selectedWorkOrderId === wo.id ? "bg-brand-50" : ""
                  }`}
                >
                  <span className="text-slate-600">
                    {new Date(wo.reading_timestamp).toUTCString()} &middot; {wo.reading_value} {tag.unit}
                  </span>
                  <span className="flex items-center gap-2">
                    <TagStatusBadge status={wo.anomaly_classification} />
                    <StatusBadge status={wo.status} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selectedWorkOrder && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-xs font-semibold uppercase text-slate-500">Investigation findings</h4>
            <Link to={`/work-orders/${selectedWorkOrder.id}`} className="text-xs text-brand-700 hover:underline">
              Open full detail &rarr;
            </Link>
          </div>
          {selectedWorkOrder.root_cause_hypothesis ? (
            <>
              <p className="text-slate-700">{selectedWorkOrder.root_cause_hypothesis}</p>
              {selectedWorkOrder.citations.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-slate-500">
                  {selectedWorkOrder.citations.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-slate-400">
              {selectedWorkOrder.anomaly_classification === "normal"
                ? "This reading was normal -- no investigation was needed."
                : "No investigation findings recorded."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
