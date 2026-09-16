import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReadingPoint } from "../api/types";
import { SensorChart } from "../components/SensorChart";

function makeReadings(): ReadingPoint[] {
  const readings: ReadingPoint[] = [];
  const base = new Date("2026-09-11T00:00:00Z").getTime();
  for (let i = 0; i < 120; i++) {
    const value = i < 100 ? 905 + (Math.random() - 0.5) * 4 : 905 + (i - 100) * 3.5;
    readings.push({ timestamp: new Date(base + i * 3600_000).toISOString(), value });
  }
  return readings;
}

describe("SensorChart", () => {
  it("renders without crashing given sample readings and a highlight", () => {
    const { container } = render(
      <SensorChart
        readings={makeReadings()}
        unit="psig"
        normalMin={850}
        normalMax={930}
        criticalMin={780}
        criticalMax={960}
        highlight={{ timestamp: "2026-09-15T19:00:00Z", value: 975.59, classification: "critical" }}
      />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders without crashing given no readings", () => {
    render(
      <SensorChart readings={[]} unit="psig" normalMin={850} normalMax={930} criticalMin={780} criticalMax={960} />,
    );
    expect(screen.getByText(/no readings available/i)).toBeInTheDocument();
  });

  it("renders without a highlight point", () => {
    const { container } = render(
      <SensorChart
        readings={makeReadings()}
        unit="degC"
        normalMin={2.5}
        normalMax={6.0}
        criticalMin={1.0}
        criticalMax={9.0}
      />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
