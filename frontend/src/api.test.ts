import { describe, expect, it } from "vitest";
import { parseDetail } from "./api";

describe("parseDetail", () => {
  it("reads plain messages", () => {
    expect(parseDetail("Family not found.", 404).message).toBe("Family not found.");
  });
  it("keeps location suggestions", () => {
    const r = parseDetail({ code: "LOCATION_NOT_RECOGNISED", message: "Not recognised", suggestions: ["Pune"] }, 422);
    expect(r.suggestions).toEqual(["Pune"]);
  });
  it("joins validation errors", () => {
    const r = parseDetail([{ loc: ["body", "email"], msg: "Value error, bad address" }], 422);
    expect(r.message).toBe("email: bad address");
  });
});