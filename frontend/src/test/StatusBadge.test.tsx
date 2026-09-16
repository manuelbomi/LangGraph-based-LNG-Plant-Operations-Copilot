import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge, TagStatusBadge } from "../components/StatusBadge";

describe("StatusBadge", () => {
  it("renders the human-readable label for each work order status", () => {
    render(<StatusBadge status="work_order_approved" />);
    expect(screen.getByText("Work order approved")).toBeInTheDocument();
  });

  it("renders awaiting_engineer_review with its label", () => {
    render(<StatusBadge status="awaiting_engineer_review" />);
    expect(screen.getByText("Awaiting engineer review")).toBeInTheDocument();
  });

  it("renders escalated and dismissed_benign distinctly from approved", () => {
    const { rerender } = render(<StatusBadge status="work_order_approved" />);
    expect(screen.getByText("Work order approved").className).toContain("emerald");

    rerender(<StatusBadge status="escalated" />);
    expect(screen.getByText("Escalated").className).toContain("rose");

    rerender(<StatusBadge status="dismissed_benign" />);
    expect(screen.getByText("Dismissed as benign")).toBeInTheDocument();
  });
});

describe("TagStatusBadge", () => {
  it("renders each equipment-health status", () => {
    const { rerender } = render(<TagStatusBadge status="normal" />);
    expect(screen.getByText("Normal").className).toContain("emerald");

    rerender(<TagStatusBadge status="warning" />);
    expect(screen.getByText("Warning").className).toContain("amber");

    rerender(<TagStatusBadge status="critical" />);
    expect(screen.getByText("Critical").className).toContain("rose");

    rerender(<TagStatusBadge status="unknown" />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});
