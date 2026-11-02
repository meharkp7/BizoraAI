import { describe, expect, it } from "vitest";
import { findPassage } from "./paperPassage.ts";
import { paperTextFixture } from "../../test/fixtures.ts";

const TEXT = paperTextFixture.text;

describe("findPassage", () => {
  it("finds an exact quote on its cited page", () => {
    const match = findPassage(TEXT, 2, "The filter corner is 4 kHz per the paper");

    expect(match.page).toBe(2);
    expect(match.pageFound).toBe(true);
    expect(match.quoteFound).toBe(true);
    expect(match.quote).toBe("The filter corner is 4 kHz per the paper");
    expect(match.after).toContain("room temperature");
  });

  it("searches the whole paper when the page marker is missing", () => {
    const match = findPassage(TEXT, 9, "Intro words");

    expect(match.page).toBeNull();
    expect(match.pageFound).toBe(false);
    expect(match.quoteFound).toBe(true);
    expect(match.quote).toBe("Intro words");
  });

  it("matches a quote whose tail differs by extraction whitespace", () => {
    const match = findPassage(
      TEXT,
      2,
      "The filter corner is 4 kHz per the paper, measured under totally different words",
    );

    expect(match.page).toBe(2);
    expect(match.quoteFound).toBe(true);
    expect(match.quote.startsWith("The filter corner is 4 kHz")).toBe(true);
  });

  it("falls back to the page head when the quote is absent", () => {
    const match = findPassage(TEXT, 2, "nothing like this appears anywhere");

    expect(match.page).toBe(2);
    expect(match.quoteFound).toBe(false);
    expect(match.after).toContain("The filter corner is 4 kHz");
  });

  it("handles unmarked text and missing quotes", () => {
    const plain = "Just some words without any page markers at all.";
    const match = findPassage(plain, null, null);

    expect(match.page).toBeNull();
    expect(match.quoteFound).toBe(false);
    expect(match.after).toBe(plain);
  });
});
