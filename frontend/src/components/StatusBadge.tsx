import { STATUS_LABELS, TAG_STATUS_LABELS, type WorkOrderStatus } from "../api/types";

const WORK_ORDER_STATUS_STYLES: Record<WorkOrderStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  running: "bg-sky-100 text-sky-700",
  awaiting_engineer_review: "bg-amber-100 text-amber-700",
  work_order_approved: "bg-emerald-100 text-emerald-700",
  escalated: "bg-rose-100 text-rose-700",
  dismissed_benign: "bg-slate-100 text-slate-500",
  normal_logged: "bg-teal-100 text-teal-700",
  error: "bg-rose-100 text-rose-700",
};

interface StatusBadgeProps {
  status: WorkOrderStatus;
}

/** A small colored pill for a work order's lifecycle status, used across
 * the work order queue and detail views. See app/db/models.py::WorkOrder for
 * the full status lifecycle this mirrors. */
export function StatusBadge({ status }: StatusBadgeProps) {
  const style = WORK_ORDER_STATUS_STYLES[status] ?? "bg-slate-100 text-slate-600";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>{STATUS_LABELS[status] ?? status}</span>;
}

const TAG_STATUS_STYLES: Record<string, string> = {
  unknown: "bg-slate-100 text-slate-500",
  normal: "bg-emerald-100 text-emerald-700",
  warning: "bg-amber-100 text-amber-700",
  critical: "bg-rose-100 text-rose-700",
};

interface TagStatusBadgeProps {
  status: string;
}

/** A small colored pill for a sensor tag's current equipment-health status
 * (normal/warning/critical/unknown), used on the plant dashboard. */
export function TagStatusBadge({ status }: TagStatusBadgeProps) {
  const style = TAG_STATUS_STYLES[status] ?? "bg-slate-100 text-slate-500";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>{TAG_STATUS_LABELS[status] ?? status}</span>;
}
