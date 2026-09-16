import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { InterruptPayload } from "../api/types";
import { ReviewForm } from "../components/ReviewForm";

const INTERRUPT: InterruptPayload = {
  tag_meta: { tag_id: "C-201-DISCH-PRESS" },
  reading_value: 975.59,
  reading_timestamp: "2026-09-15T19:00:00+00:00",
  anomaly_classification: "critical",
  anomaly_details: {
    rolling_mean: 928.6,
    rolling_std: 23.2,
    z_score: 2.02,
    rate_per_hour: 0.78,
    stuck_detected: false,
    threshold_breach: "critical_high",
    history_window_size: 168,
    reasons: ["value 975.59 breaches critical threshold (critical_high)"],
  },
  retrieved_context: [],
  root_cause_hypothesis: "Likely progressive fouling downstream of the compressor.",
  recommended_response: "Inspect the discharge check valve and strainers.",
  citations: ["Manual: Compressor C-201 Discharge Pressure High: Possible Causes and Response Procedure"],
  draft_work_order: {
    tag_id: "C-201-DISCH-PRESS",
    tag_name: "Compressor C-201 Discharge Pressure",
    equipment_id: "C-201",
    equipment_name: "Process Gas Compressor C-201",
    observed_anomaly: "Compressor C-201 Discharge Pressure reading of 975.59 psig, classified CRITICAL.",
    severity: "critical",
    title: "Investigate critical discharge pressure drift on C-201",
    description: "Draft description referencing root cause and recommended action.",
    recommended_action: "Cross-check downstream flow, inspect anti-surge valve.",
    priority: "urgent",
  },
};

describe("ReviewForm", () => {
  it("pre-fills the draft work order fields", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByLabelText(/work order title/i)).toHaveValue(
      "Investigate critical discharge pressure drift on C-201",
    );
    expect(screen.getByLabelText(/^description$/i)).toHaveValue(
      "Draft description referencing root cause and recommended action.",
    );
    expect(screen.getByLabelText(/priority/i)).toHaveValue("urgent");
  });

  it("shows the decision-support-only safety banner", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);
    expect(screen.getByText(/does not control any equipment/i)).toBeInTheDocument();
  });

  it("displays the root-cause hypothesis and citations", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);
    expect(screen.getByText(/progressive fouling/i)).toBeInTheDocument();
    expect(screen.getByText(/Manual: Compressor C-201/i)).toBeInTheDocument();
  });

  it("calls onDecision with approve and the corrected draft", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "approve",
        feedback: "",
        corrected_draft_work_order: expect.objectContaining({ priority: "urgent" }),
      }),
    );
  });

  it("calls onDecision with escalate and the engineer note as feedback", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.type(screen.getByLabelText(/engineer note/i), "Escalating immediately, safety-relevant.");
    await user.click(screen.getByRole("button", { name: /^escalate$/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({ decision: "escalate", feedback: "Escalating immediately, safety-relevant." }),
    );
  });

  it("calls onDecision with dismiss_benign", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(screen.getByRole("button", { name: /dismiss as benign/i }));

    expect(onDecision).toHaveBeenCalledWith(expect.objectContaining({ decision: "dismiss_benign" }));
  });

  it("sends edited fields in corrected_draft_work_order", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    const description = screen.getByLabelText(/^description$/i);
    await user.clear(description);
    await user.type(description, "Edited description with engineer clarifications.");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        corrected_draft_work_order: expect.objectContaining({
          description: "Edited description with engineer clarifications.",
        }),
      }),
    );
  });

  it("disables the buttons while submitting", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} submitting />);

    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^escalate$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /dismiss as benign/i })).toBeDisabled();
  });
});
