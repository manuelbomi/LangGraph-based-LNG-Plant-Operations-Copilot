import type {
  HumanDecisionRequest,
  ReadingsResponse,
  SamplesResponse,
  SensorTagDetail,
  SensorTagListResponse,
  WorkOrderCreateResponse,
  WorkOrderDetail,
  WorkOrderListResponse,
} from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function listTags(): Promise<SensorTagListResponse> {
  const res = await fetch(`${API_BASE_URL}/tags`);
  return handle<SensorTagListResponse>(res);
}

export async function getTag(tagId: string): Promise<SensorTagDetail> {
  const res = await fetch(`${API_BASE_URL}/tags/${encodeURIComponent(tagId)}`);
  return handle<SensorTagDetail>(res);
}

export async function getTagReadings(
  tagId: string,
  opts?: { hours?: number; end?: string },
): Promise<ReadingsResponse> {
  const query = new URLSearchParams();
  if (opts?.hours) query.set("hours", String(opts.hours));
  if (opts?.end) query.set("end", opts.end);
  const qs = query.toString();
  const res = await fetch(`${API_BASE_URL}/tags/${encodeURIComponent(tagId)}/readings${qs ? `?${qs}` : ""}`);
  return handle<ReadingsResponse>(res);
}

export async function listSamples(): Promise<SamplesResponse> {
  const res = await fetch(`${API_BASE_URL}/work-orders/samples`);
  return handle<SamplesResponse>(res);
}

export async function runSampleAnomaly(sampleId: string): Promise<WorkOrderCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/work-orders/samples/${encodeURIComponent(sampleId)}/run`, {
    method: "POST",
  });
  return handle<WorkOrderCreateResponse>(res);
}

export async function runReading(tagId: string, timestamp: string): Promise<WorkOrderCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/work-orders/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag_id: tagId, timestamp }),
  });
  return handle<WorkOrderCreateResponse>(res);
}

export async function resumeWorkOrder(
  workOrderId: string,
  payload: HumanDecisionRequest,
): Promise<WorkOrderCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/work-orders/${encodeURIComponent(workOrderId)}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<WorkOrderCreateResponse>(res);
}

export async function listWorkOrders(params?: {
  tagId?: string;
  status?: string;
}): Promise<WorkOrderListResponse> {
  const query = new URLSearchParams();
  if (params?.tagId) query.set("tag_id", params.tagId);
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  const res = await fetch(`${API_BASE_URL}/work-orders${qs ? `?${qs}` : ""}`);
  return handle<WorkOrderListResponse>(res);
}

export async function getWorkOrder(workOrderId: string): Promise<WorkOrderDetail> {
  const res = await fetch(`${API_BASE_URL}/work-orders/${encodeURIComponent(workOrderId)}`);
  return handle<WorkOrderDetail>(res);
}

export function streamUrl(workOrderId: string): string {
  return `${API_BASE_URL}/work-orders/${encodeURIComponent(workOrderId)}/stream`;
}
