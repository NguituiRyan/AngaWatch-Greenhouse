import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskBadge, StatusPill } from "./Badge";

describe("Badge components", () => {
  it("renders a humanized risk level", () => {
    render(<RiskBadge level="high" />);
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders a status pill label", () => {
    render(<StatusPill label="Active" tone="green" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
});
