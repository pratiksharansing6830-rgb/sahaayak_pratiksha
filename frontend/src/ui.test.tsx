import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiError } from "./api";
import { CITIZEN_MOVES, ErrorBox, NEED_TONE, NeedBadge } from "./ui";

afterEach(cleanup);

describe("status display", () => {
  it("uses green only for confirmed support", () => {
    const green = Object.entries(NEED_TONE).filter(([, t]) => t === "green").map(([s]) => s);
    expect(green).toEqual(["SUPPORT_CONFIRMED"]);
  });
  it("shows a plain-language label", () => {
    render(<NeedBadge status="BARRIER_IDENTIFIED" />);
    expect(screen.getByText("Something is blocking support")).toBeTruthy();
  });
  it("never lets a citizen pick confirmed support from the status menu", () => {
    for (const targets of Object.values(CITIZEN_MOVES)) expect(targets).not.toContain("SUPPORT_CONFIRMED");
  });
});

describe("ErrorBox", () => {
  it("offers location suggestions", () => {
    render(<ErrorBox error={new ApiError(422, "Not recognised", ["Pune"])} />);
    expect(screen.getByText("Pune")).toBeTruthy();
  });
});