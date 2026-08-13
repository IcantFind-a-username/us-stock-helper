import { describe, expect, it } from "@jest/globals";

import { marketErrorCategories } from "@/data/marketRepository";
import { describeMarketError } from "@/i18n/marketErrorCopy";

/**
 * The App is read by one person, in Chinese. A screen that prints the wire
 * identifier of a failure — `malformed`, `ANALYSIS_FAILED` — has told him
 * nothing, so these tests hold the copy table to being complete, mutually
 * distinguishable, and written in the language he reads.
 */

const CJK = /[一-鿿]/;

describe("describeMarketError", () => {
  it("answers every category with Chinese copy", () => {
    for (const category of marketErrorCategories) {
      const copy = describeMarketError(category);
      expect(CJK.test(copy.label)).toBe(true);
      expect(CJK.test(copy.title)).toBe(true);
      expect(CJK.test(copy.body)).toBe(true);
      // The row label sits in a 74pt column at 8pt type; a long one truncates
      // into something that reads as a different word.
      expect(copy.label.length).toBeLessThanOrEqual(5);
      expect(copy.body.length).toBeGreaterThanOrEqual(20);
    }
  });

  it("never prints the wire identifier back at the reader", () => {
    for (const category of marketErrorCategories) {
      const copy = describeMarketError(category);
      const rendered = `${copy.label}${copy.title}${copy.body}`;
      expect(rendered).not.toContain(category);
      expect(rendered).not.toContain(category.toUpperCase().replace("-", "_"));
    }
  });

  it("keeps every category distinguishable from every other", () => {
    const labels = marketErrorCategories.map(
      (category) => describeMarketError(category).label,
    );
    const titles = marketErrorCategories.map(
      (category) => describeMarketError(category).title,
    );
    const bodies = marketErrorCategories.map(
      (category) => describeMarketError(category).body,
    );

    expect(new Set(labels).size).toBe(marketErrorCategories.length);
    expect(new Set(titles).size).toBe(marketErrorCategories.length);
    expect(new Set(bodies).size).toBe(marketErrorCategories.length);
  });

  it("explains a point-in-time rejection as the gateway doing its job", () => {
    const copy = describeMarketError("malformed");

    // This is the failure that hides three symbols on a 46-symbol watchlist.
    // The reader has to learn what was rejected, that the rejection was
    // deliberate, and that he did not cause it.
    // The gateway rejects on roughly twenty distinct checks and reports none
    // of them, so naming one would be inventing the reason.
    expect(copy.title).toContain("没通过校验");
    expect(copy.body).toContain("没有说明具体是哪一项");
    for (const invented of ["时序", "倒序", "重复的时间戳", "可获得时间"]) {
      expect(copy.body).not.toContain(invented);
    }
    expect(copy.body).toContain("不准确");
    expect(copy.body).toContain("不是你的操作");
    // It must not read as a verdict on the company.
    expect(copy.body).toContain("供应商");
  });

  it("separates a declined analysis from a rejected payload", () => {
    const failed = describeMarketError("analysis-failed");
    const malformed = describeMarketError("malformed");

    expect(failed.title).not.toBe(malformed.title);
    // The analysis service masks its upstream cause on purpose, so this copy
    // must not borrow the market gateway's explanation for it.
    expect(failed.title).not.toContain("时序校验");
    expect(failed.body).not.toContain("时序校验");
    expect(failed.body).toContain("没有说明");
  });

  it("tells a stalled OpenD login apart from an unpaired phone", () => {
    const openD = describeMarketError("login-required");
    const device = describeMarketError("auth-required");

    // The two used to share a category, and their remedies have nothing in
    // common: one is a login on the Mac, the other is a pairing code.
    expect(openD.body).toContain("OpenD");
    expect(openD.body).not.toContain("配对");
    expect(device.body).toContain("配对");
    expect(device.body).not.toContain("OpenD");
  });

  it("refuses to invent a reason the server did not give", () => {
    const copy = describeMarketError("unspecified");

    expect(copy.body).toContain("没有");
    expect(copy.body).toContain("不做猜测");
  });

  it("rejects a category it has no copy for", () => {
    expect(() =>
      describeMarketError("not-a-category" as (typeof marketErrorCategories)[number]),
    ).toThrow();
  });
});
