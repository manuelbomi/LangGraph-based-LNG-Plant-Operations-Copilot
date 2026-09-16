import { Background, type Edge, Handle, type Node, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import { GRAPH_NODE_LABELS, GRAPH_NODES, type GraphNodeName } from "../api/types";

interface GraphViewProps {
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
}

interface NodeData extends Record<string, unknown> {
  label: string;
  active: boolean;
  done: boolean;
}

function StepNode({ data }: { data: NodeData }) {
  const base =
    "rounded-lg border-2 px-3 py-2 text-sm font-medium shadow-sm min-w-[170px] text-center transition-colors";
  const cls = data.active
    ? `${base} border-brand-500 bg-brand-500 text-white animate-pulse`
    : data.done
      ? `${base} border-brand-300 bg-brand-50 text-brand-800`
      : `${base} border-slate-300 bg-white text-slate-500`;
  return (
    <div className={cls}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      {data.label}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
      <Handle type="source" position={Position.Right} id="right" className="!bg-slate-400" />
      <Handle type="target" position={Position.Left} id="left" className="!bg-slate-400" />
    </div>
  );
}

const nodeTypes = { step: StepNode };

/** This graph has REAL conditional routing after `detect_anomaly` -- a
 * `normal` classification branches off to `log_normal` (a short dead-end),
 * while `warning`/`critical` continues down the main investigate/draft/
 * review/finalize line. The layout reflects that fork explicitly. */
const LAYOUT: Record<GraphNodeName, { x: number; y: number }> = {
  ingest_reading: { x: 40, y: 0 },
  detect_anomaly: { x: 40, y: 100 },
  log_normal: { x: 280, y: 200 },
  investigate: { x: 40, y: 220 },
  draft_work_order: { x: 40, y: 320 },
  engineer_review: { x: 40, y: 420 },
  finalize: { x: 40, y: 520 },
};

export function GraphView({ currentNode, completedNodes }: GraphViewProps) {
  const nodes: Node[] = useMemo(
    () =>
      GRAPH_NODES.map((id, index) => ({
        id,
        type: "step",
        position: LAYOUT[id],
        data: {
          label: `${index + 1}. ${GRAPH_NODE_LABELS[id]}`,
          active: currentNode === id,
          done: completedNodes.includes(id) && currentNode !== id,
        } satisfies NodeData,
        draggable: false,
      })),
    [currentNode, completedNodes],
  );

  const edgeStyle = (active: boolean) => ({
    stroke: active ? "#265d9c" : "#cbd5e1",
    strokeWidth: active ? 2.5 : 1.5,
  });

  const edges: Edge[] = useMemo(() => {
    const pairs: [GraphNodeName, GraphNodeName][] = [
      ["ingest_reading", "detect_anomaly"],
      ["detect_anomaly", "log_normal"],
      ["detect_anomaly", "investigate"],
      ["investigate", "draft_work_order"],
      ["draft_work_order", "engineer_review"],
      ["engineer_review", "finalize"],
    ];
    return pairs.map(([source, target]) => ({
      id: `e-${source}-${target}`,
      source,
      target,
      sourceHandle: target === "log_normal" ? "right" : undefined,
      targetHandle: target === "log_normal" ? "left" : undefined,
      style: edgeStyle(completedNodes.includes(target)),
      label: source === "detect_anomaly" && target === "log_normal" ? "normal" : source === "detect_anomaly" ? "warning/critical" : undefined,
      labelStyle: { fontSize: 10, fill: "#64748b" },
    }));
  }, [completedNodes]);

  return (
    <div className="h-[620px] w-full rounded-xl border border-slate-200 bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={16} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}
