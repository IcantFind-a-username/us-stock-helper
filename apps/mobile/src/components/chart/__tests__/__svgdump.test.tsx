import { writeFileSync } from "fs";

import { expect, it } from "@jest/globals";
import { render } from "@testing-library/react-native";

import { buildChartGeometry } from "@/domain/chart";
import type { Candle } from "@/domain/models";

import { ChartCanvas } from "../ChartCanvas";

const width = 334;
const height = 460;
const svgDump = process.env.SVG_OUT ? it : it.skip;

let seed = 7;
const random = () => {
  seed = (seed * 1103515245 + 12345) % 2147483648;
  return seed / 2147483648;
};

let price = 141;
const candles: Candle[] = Array.from({ length: 260 }, (_, index) => {
  const timestamp = new Date(Date.UTC(2026, 6, 24, 13, 30 + index * 5)).toISOString();
  const open = price;
  const drift = (random() - 0.48) * 0.9;
  const close = open + drift;
  price = close;
  return {
    timestamp,
    availableAt: new Date(Date.parse(timestamp) + 1_000).toISOString(),
    complete: true,
    open,
    high: Math.max(open, close) + random() * 0.5,
    low: Math.min(open, close) - random() * 0.5,
    close,
    volume: 1_000 + Math.round(random() * 4_000),
  };
});

const colour = (value: unknown) => {
  const payload = (value as { payload?: number } | null)?.payload;
  if (typeof payload !== "number") return null;
  const alpha = ((payload >>> 24) & 255) / 255;
  const hex = `#${(payload & 0xffffff).toString(16).padStart(6, "0")}`;
  return { hex, alpha };
};

const paint = (props: Record<string, unknown>, key: "fill" | "stroke") => {
  const parsed = colour(props[key]);
  if (!parsed) return "";
  const opacity = props[`${key}Opacity`];
  const total = parsed.alpha * (typeof opacity === "number" ? opacity : 1);
  return ` ${key}="${parsed.hex}" ${key}-opacity="${total}"`;
};

const numeric = (props: Record<string, unknown>, keys: string[]) =>
  keys
    .filter((key) => typeof props[key] === "number" || typeof props[key] === "string")
    .map((key) => ` ${key.replace(/([A-Z])/g, "-$1").toLowerCase()}="${String(props[key])}"`)
    .join("");

const text = (node: unknown): string => {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(text).join("");
  const element = node as
    | { props?: { content?: unknown }; children?: unknown[] }
    | null;
  const own =
    typeof element?.props?.content === "string" ? element.props.content : "";
  return own + (element?.children ?? []).map(text).join("");
};

const toSvg = (node: unknown): string => {
  if (typeof node === "string") return "";
  if (Array.isArray(node)) return node.map(toSvg).join("");
  if (!node || typeof node !== "object") return "";
  const element = node as {
    type?: string;
    props?: Record<string, unknown>;
    children?: unknown[];
  };
  const props = element.props ?? {};
  const children = (element.children ?? []).map(toSvg).join("");
  const dash =
    props.strokeDasharray === undefined
      ? ""
      : ` stroke-dasharray="${[props.strokeDasharray].flat().join(" ")}"`;
  switch (element.type) {
    case "RNSVGSvgView":
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${props.vbWidth}" height="${props.vbHeight}" viewBox="0 0 ${props.vbWidth} ${props.vbHeight}" style="background:#FFFFFF">${children}</svg>`;
    case "RNSVGGroup":
      return `<g>${children}</g>`;
    case "RNSVGLine":
      return `<line${numeric(props, ["x1", "y1", "x2", "y2", "strokeWidth"])}${paint(props, "stroke")}${dash}/>`;
    case "RNSVGRect":
      return `<rect${numeric(props, ["x", "y", "width", "height", "rx"])}${paint(props, "fill")}/>`;
    case "RNSVGPath":
      return `<path d="${String(props.d)}"${numeric(props, ["strokeWidth"])}${paint(props, "stroke")}${dash} fill="none"/>`;
    case "RNSVGText": {
      const font = (props.font ?? {}) as Record<string, unknown>;
      const anchor = font.textAnchor ? ` text-anchor="${String(font.textAnchor)}"` : "";
      return `<text x="${[props.x].flat()[0]}" y="${[props.y].flat()[0]}" font-size="${String(font.fontSize ?? 10)}"${anchor}${paint(props, "fill")} font-family="Helvetica">${text(element)}</text>`;
    }
    default:
      return children;
  }
};

svgDump("dumps the canvas for a human to look at", async () => {
  const geometry = buildChartGeometry({
    candles,
    forecast: null,
    participationBars: [],
    decisionCutoff: "2026-07-25T23:00:00.000Z",
    width,
    height,
    panels: ["volume", "macd", "rsi"],
    overlays: [
      {
        key: "ma5",
        label: "MA5",
        values: candles.map((candle, index) =>
          index < 4
            ? null
            : candles
                .slice(index - 4, index + 1)
                .reduce((sum, entry) => sum + entry.close, 0) / 5,
        ),
      },
    ],
    macdSeries: {
      line: candles.map((_, index) => Math.sin(index / 9) * 0.4),
      signal: candles.map((_, index) => Math.sin(index / 9 - 0.6) * 0.35),
      histogram: candles.map(
        (_, index) => Math.sin(index / 9) * 0.4 - Math.sin(index / 9 - 0.6) * 0.35,
      ),
    },
    rsiSeries: { values: candles.map((_, index) => 50 + Math.sin(index / 7) * 22) },
    window: null,
  });

  const view = await render(
    <ChartCanvas
      geometry={geometry}
      height={height}
      macdLabel="MACD(12,26,9) DIF 0.12 DEA 0.08"
      markers={[]}
      rsiLabel="RSI(14) 56.2"
      selectedX={null}
      showForecast={false}
      showParticipation={false}
      width={width}
    />,
  );

  const body = toSvg(view.toJSON());
  writeFileSync(process.env.SVG_OUT!, body);
  expect(body).toContain("<rect");
});
