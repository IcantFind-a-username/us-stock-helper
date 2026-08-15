import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "@jest/globals";

import {
  decodeStockSnapshotEnvelope,
  decodeStockSnapshotV3Envelope,
} from "../marketGateway";

/**
 * Cross-language contract fixtures.
 *
 * F9 (see 2c54997, "fix: decode the macd series shape the gateway actually
 * sends"): decodeMacdSeries and its hand-built TypeScript fixtures once
 * agreed on the *same wrong* nested `{ series: { line, signal, histogram } }`
 * shape, so every mobile test stayed green while a real, live snapshot
 * silently drew nothing -- the fixture and the decoder drifted together
 * against the gateway, not against each other.
 *
 * These two files are generated on the Python side by
 * services/market_gateway/tests/test_snapshot_contract_v3.py, which drives
 * the real MarketGatewayService end to end over a fixed bar series and
 * writes the byte-for-byte output to fixtures/contract_snapshot_v3.json
 * (and _v2.json). Reading that exact file here -- rather than hand-writing
 * a TypeScript object literal -- means a gateway serializer change can no
 * longer drift the fixture along with the decoder: it either breaks the
 * Python byte-equality test (forcing a fixture regeneration commit) or it
 * breaks the decode assertions below.
 */

const REPO_ROOT = join(__dirname, "..", "..", "..", "..", "..");
const CONTRACT_V3_PATH = join(
  REPO_ROOT,
  "services/market_gateway/tests/fixtures/contract_snapshot_v3.json",
);
const CONTRACT_V2_PATH = join(
  REPO_ROOT,
  "services/market_gateway/tests/fixtures/contract_snapshot_v2.json",
);

function readContractFixture(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf8"));
}

describe("cross-language snapshot contract (gateway-generated fixtures)", () => {
  it("decodes the gateway-generated v3 snapshot as a fully live contract", () => {
    const payload = readContractFixture(CONTRACT_V3_PATH);

    const snapshot = decodeStockSnapshotV3Envelope(payload);

    expect(snapshot.snapshotStatus).toBe("live");
    expect(snapshot.compatibility).toBe("v3");
    const candleCount = snapshot.candles.length;
    expect(candleCount).toBeGreaterThan(0);

    // MACD: the exact shape 2c54997 fixed. Before that fix, decodeMacdSeries
    // read the (always-absent) nested `macdRecord.series` field, so `series`
    // silently decoded to null on this same live payload -- see the RED
    // check documented in the implementation report for this file.
    expect(snapshot.indicators.macd.qualityStatus).toBe("live");
    expect(snapshot.indicators.macd.series).not.toBeNull();
    expect(snapshot.indicators.macd.series!.line).toHaveLength(candleCount);
    expect(snapshot.indicators.macd.series!.signal).toHaveLength(candleCount);
    expect(snapshot.indicators.macd.series!.histogram).toHaveLength(
      candleCount,
    );
    // The published single value is the last series position -- pinning
    // this catches a decoder that reads a shifted or misaligned array just
    // as surely as one that reads the wrong field entirely.
    expect(snapshot.indicators.macd.series!.line.at(-1)).toBe(
      snapshot.indicators.macd.line,
    );
    expect(snapshot.indicators.macd.series!.signal.at(-1)).toBe(
      snapshot.indicators.macd.signal,
    );
    expect(snapshot.indicators.macd.series!.histogram.at(-1)).toBe(
      snapshot.indicators.macd.histogram,
    );

    expect(snapshot.indicators.rsi.qualityStatus).toBe("live");
    expect(snapshot.indicators.rsi.series).not.toBeNull();
    expect(snapshot.indicators.rsi.series!.values).toHaveLength(candleCount);
    expect(snapshot.indicators.rsi.series!.values.at(-1)).toBe(
      snapshot.indicators.rsi.value,
    );

    expect(snapshot.indicators.ma5.series).not.toBeNull();
    expect(snapshot.indicators.ma5.series!.values).toHaveLength(candleCount);

    // patternShapes: decodes real detections with real signals, not just an
    // empty-but-well-formed array.
    expect(snapshot.indicators.patternShapes.qualityStatus).toBe("live");
    expect(snapshot.indicators.patternShapes.detections.length).toBeGreaterThan(0);
    const totalSignals = snapshot.indicators.patternShapes.detections.reduce(
      (sum, detection) => sum + detection.signals.length,
      0,
    );
    expect(totalSignals).toBeGreaterThan(0);

    expect(snapshot.magicNine.qualityStatus).toBe("live");
    expect(snapshot.magicNine.series).not.toBeNull();
    expect(snapshot.magicNine.series).toHaveLength(candleCount);

    expect(snapshot.sections.currentSessionFlow.qualityStatus).toBe(
      "validated",
    );
    expect(snapshot.participationBars).toHaveLength(candleCount);

    expect(snapshot.institutionalHoldings.length).toBeGreaterThan(0);
  });

  it("decodes the gateway-generated v2 snapshot as a fully live contract", () => {
    const payload = readContractFixture(CONTRACT_V2_PATH);

    const snapshot = decodeStockSnapshotEnvelope(payload);

    expect(snapshot.snapshotStatus).toBe("live");
    expect(snapshot.compatibility).toBe("v2-fallback");
    const candleCount = snapshot.candles.length;
    expect(candleCount).toBeGreaterThan(0);

    expect(snapshot.indicators.macd.qualityStatus).toBe("live");
    expect(snapshot.indicators.macd.series).not.toBeNull();
    expect(snapshot.indicators.macd.series!.line).toHaveLength(candleCount);
    expect(snapshot.indicators.macd.series!.line.at(-1)).toBe(
      snapshot.indicators.macd.line,
    );

    expect(snapshot.indicators.rsi.series).not.toBeNull();
    expect(snapshot.indicators.rsi.series!.values).toHaveLength(candleCount);

    expect(
      snapshot.indicators.patternShapes.detections.some(
        (detection) => detection.signals.length > 0,
      ),
    ).toBe(true);

    expect(snapshot.magicNine.qualityStatus).toBe("live");
    expect(snapshot.institutionalHoldings.length).toBeGreaterThan(0);
  });

  it("would have caught the pre-2c54997 nested macd shape (regression guard)", () => {
    // Reproduces the exact historical defect on the real gateway-generated
    // payload: the old wire contract this decoder briefly (and wrongly)
    // assumed. A gateway that regressed to publishing this nested shape
    // instead of the flat lineSeries/signalSeries/histogramSeries fields
    // must degrade the chart's MACD series to unavailable rather than
    // silently draw from a field the gateway never sends.
    const payload = readContractFixture(CONTRACT_V3_PATH) as {
      sections: {
        technical: {
          data: { indicators: { macd: Record<string, unknown> } };
        };
      };
    };
    const macd = payload.sections.technical.data.indicators.macd;
    const { lineSeries, signalSeries, histogramSeries, ...rest } = macd;
    payload.sections.technical.data.indicators.macd = {
      ...rest,
      series: { line: lineSeries, signal: signalSeries, histogram: histogramSeries },
    };

    const snapshot = decodeStockSnapshotV3Envelope(payload);

    expect(snapshot.indicators.macd.series).toBeNull();
  });
});
