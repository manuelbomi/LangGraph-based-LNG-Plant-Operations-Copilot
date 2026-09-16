import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GraphView } from "../components/GraphView";

describe("GraphView", () => {
  it("renders without crashing with no active run", () => {
    const { container } = render(<GraphView currentNode={null} completedNodes={[]} />);
    expect(container.querySelector(".react-flow")).toBeInTheDocument();
  });

  it("renders the normal branch as completed without touching investigate/draft/review", () => {
    const { getByText } = render(
      <GraphView currentNode="log_normal" completedNodes={["ingest_reading", "detect_anomaly", "log_normal"]} />,
    );
    expect(getByText(/Log Normal/i)).toBeInTheDocument();
    expect(getByText(/Detect Anomaly/i)).toBeInTheDocument();
  });

  it("renders the warning/critical branch nodes", () => {
    const { getByText } = render(
      <GraphView
        currentNode="engineer_review"
        completedNodes={["ingest_reading", "detect_anomaly", "investigate", "draft_work_order", "engineer_review"]}
      />,
    );
    expect(getByText(/Engineer Review/i)).toBeInTheDocument();
    expect(getByText(/Draft Work Order/i)).toBeInTheDocument();
  });
});
