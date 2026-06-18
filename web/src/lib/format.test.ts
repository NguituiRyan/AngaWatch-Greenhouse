import { describe, expect, it } from "vitest";

import { highestRisk, humanize, metricValue, RISK_BADGE } from "./format";

describe("format helpers", () => {
  it("humanizes snake_case enum values", () => {
    expect(humanize("late_blight")).toBe("Late Blight");
    expect(humanize("tuta_absoluta")).toBe("Tuta Absoluta");
  });

  it("formats metric values with units and dashes for null", () => {
    expect(metricValue(23.456, "°C")).toBe("23.5 °C");
    expect(metricValue(80, "%", 0)).toBe("80 %");
    expect(metricValue(null, "%")).toBe("—");
  });

  it("picks the highest risk level", () => {
    expect(highestRisk(["none", "medium", "low"])).toBe("medium");
    expect(highestRisk(["low", "critical", "high"])).toBe("critical");
    expect(highestRisk([])).toBe("none");
  });

  it("maps every risk level to a badge style", () => {
    for (const level of ["none", "low", "medium", "high", "critical"] as const) {
      expect(RISK_BADGE[level]).toBeTruthy();
    }
  });
});
