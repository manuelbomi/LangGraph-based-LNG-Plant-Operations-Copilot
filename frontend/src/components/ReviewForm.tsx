import { useState } from "react";

import type { DraftWorkOrder, HumanDecision, HumanDecisionRequest, InterruptPayload } from "../api/types";

interface ReviewFormProps {
  interrupt: InterruptPayload;
  onDecision: (decision: HumanDecisionRequest) => void;
  submitting?: boolean;
}

const PRIORITY_OPTIONS: DraftWorkOrder["priority"][] = ["low", "medium", "high", "urgent"];

/** The human-in-the-loop engineer review panel -- the mandatory safety gate
 * this whole app is built around. This is decision support only: it does
 * NOT control any equipment and does NOT make a final safety-critical
 * decision. Nothing drafted here is an approved work order until a
 * qualified engineer explicitly approves, escalates, or dismisses it as
 * benign. See the root README's "Scope & Safety" section. */
export function ReviewForm({ interrupt, onDecision, submitting }: ReviewFormProps) {
  const draft = interrupt.draft_work_order;
  const [title, setTitle] = useState(draft.title);
  const [description, setDescription] = useState(draft.description);
  const [recommendedAction, setRecommendedAction] = useState(draft.recommended_action);
  const [priority, setPriority] = useState(draft.priority);
  const [feedback, setFeedback] = useState("");

  const buildCorrectedDraft = (): DraftWorkOrder => ({
    ...draft,
    title,
    description,
    recommended_action: recommendedAction,
    priority,
  });

  const submit = (decision: HumanDecision) => {
    const payload: HumanDecisionRequest = { decision, feedback };
    payload.corrected_draft_work_order = buildCorrectedDraft();
    onDecision(payload);
  };

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-700">Engineer review required</h3>
      <p className="mb-4 text-sm text-amber-900">
        <strong>Decision support only -- this does not control any equipment.</strong> This copilot drafted a
        root-cause hypothesis and work order from sensor data and the plant's own manuals/incident history; it
        does not take any physical action and does not make a final safety-critical decision. Review and correct
        the fields below as needed, then Approve, Escalate, or Dismiss as Benign. Nothing is logged as an
        official work order until you decide.
      </p>

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <div className="space-y-3 rounded-lg border border-amber-200 bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-500">Draft work order (editable)</h4>

          <div className="grid grid-cols-2 gap-2 text-xs text-slate-500">
            <div>
              <span className="block">Equipment</span>
              <span className="text-slate-700">{draft.equipment_name}</span>
            </div>
            <div>
              <span className="block">Severity</span>
              <span className="text-slate-700">{draft.severity}</span>
            </div>
          </div>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Title</span>
            <input
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              aria-label="Work order title"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Priority</span>
            <select
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              aria-label="Priority"
            >
              {PRIORITY_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Description</span>
            <textarea
              className="mt-0.5 w-full rounded border border-slate-300 p-2"
              rows={6}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              aria-label="Description"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Recommended action</span>
            <textarea
              className="mt-0.5 w-full rounded border border-slate-300 p-2"
              rows={3}
              value={recommendedAction}
              onChange={(e) => setRecommendedAction(e.target.value)}
              aria-label="Recommended action"
            />
          </label>
        </div>

        <div className="space-y-3">
          <div className="rounded-lg border border-amber-200 bg-white p-4 text-sm">
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Root-cause hypothesis</h4>
            <p className="text-slate-700">{interrupt.root_cause_hypothesis || "(none)"}</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-white p-4 text-sm">
            <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Recommended response</h4>
            <p className="text-slate-700">{interrupt.recommended_response || "(none)"}</p>
          </div>
          {interrupt.citations.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Citations</h4>
              <ul className="list-disc space-y-1 pl-4 text-xs text-slate-600">
                {interrupt.citations.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      <textarea
        className="mb-3 w-full rounded-md border border-slate-300 p-2 text-sm"
        rows={2}
        placeholder="Engineer note (optional) -- why you approved, escalated, or dismissed this anomaly"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        aria-label="Engineer note"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("approve")}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("escalate")}
          className="rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
        >
          Escalate
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("dismiss_benign")}
          className="rounded-md bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Dismiss as Benign
        </button>
      </div>
    </div>
  );
}
