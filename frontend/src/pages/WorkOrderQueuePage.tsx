import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { listWorkOrders } from "../api/client";
import { STATUS_LABELS, TAG_STATUS_LABELS, type WorkOrderStatus } from "../api/types";
import { StatusBadge, TagStatusBadge } from "../components/StatusBadge";

const STATUS_FILTERS: WorkOrderStatus[] = [
  "awaiting_engineer_review",
  "work_order_approved",
  "escalated",
  "dismissed_benign",
  "normal_logged",
];

/** The work order queue / example-analyses view: every anomaly event ever
 * processed (plus the seeded example events), with status badges and a
 * link into the per-event detail view. This is the key out-of-the-box
 * example-analysis page -- it works against the seeded data with no setup. */
export function WorkOrderQueuePage() {
  const [statusFilter, setStatusFilter] = useState<string>("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["work-orders", statusFilter],
    queryFn: () => listWorkOrders({ status: statusFilter || undefined }),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Work Order Queue</h2>
        <label className="text-sm">
          <span className="sr-only">Filter by status</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading work orders...</p>}
      {error && <p className="text-sm text-rose-600">Could not load work orders.</p>}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Created</th>
                <th className="px-4 py-2">Equipment</th>
                <th className="px-4 py-2">Tag</th>
                <th className="px-4 py-2">Reading</th>
                <th className="px-4 py-2">Classification</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.work_orders.map((wo) => (
                <tr key={wo.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-2 align-top text-xs text-slate-500">
                    {new Date(wo.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 align-top">
                    <Link to={`/work-orders/${wo.id}`} className="font-medium text-brand-700 hover:underline">
                      {wo.equipment_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2 align-top font-mono text-xs text-slate-500">{wo.tag_id}</td>
                  <td className="px-4 py-2 align-top text-xs text-slate-600">{wo.reading_value}</td>
                  <td className="px-4 py-2 align-top">
                    {wo.anomaly_classification ? (
                      <TagStatusBadge status={wo.anomaly_classification} />
                    ) : (
                      <span className="text-xs text-slate-400">{TAG_STATUS_LABELS.unknown}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 align-top">
                    <StatusBadge status={wo.status} />
                  </td>
                </tr>
              ))}
              {data.work_orders.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-sm text-slate-400">
                    No work orders yet -- trigger a sample reading from the Plant Dashboard.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
