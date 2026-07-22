/*
 * Shared inline-SVG chart geometry/rendering helpers for the Weight Coach
 * cards. No charting library - self-contained, styled entirely via CSS
 * custom properties so it themes correctly under Catppuccin Latte/Frappé
 * (or any other HA theme) automatically.
 *
 * Time-based (not index-based) x scale, since weigh-in/intake dates are
 * irregularly spaced. `smoothPath` is a Catmull-Rom-to-cubic-Bezier
 * converter, kept consistent with the one already used by
 * energy-budget-forecast-chart-card.js elsewhere in this config.
 */

/** Parse a "YYYY-MM-DD" date string as local midnight (avoids TZ off-by-one
 * that `new Date("YYYY-MM-DD")` (parsed as UTC) can cause). */
export function parseYMD(dateStr) {
  return new Date(`${dateStr}T00:00:00`).getTime();
}

/**
 * Compute x/y scaling functions for a chart plotting `data` (an array of
 * `{date, ...}` objects) over a `width`x`height` SVG viewport.
 *
 * @param {Array<{date: string}>} data
 * @param {{width:number,height:number,padTop?:number,padRight?:number,padBottom?:number,padLeft?:number,valueKeys?:string[],extraValues?:number[]}} opts
 */
export function computeGeometry(data, opts) {
  const {
    width,
    height,
    padTop = 12,
    padRight = 12,
    padBottom = 24,
    padLeft = 40,
    valueKeys = [],
    extraValues = [],
  } = opts;

  const plotWidth = Math.max(1, width - padLeft - padRight);
  const plotHeight = Math.max(1, height - padTop - padBottom);

  const times = data.map((d) => parseYMD(d.date));
  const minT = times.length ? Math.min(...times) : 0;
  const maxT = times.length ? Math.max(...times) : 1;
  const spanT = maxT - minT || 1;

  const values = [];
  for (const d of data) {
    for (const key of valueKeys) {
      if (Number.isFinite(d[key])) values.push(d[key]);
    }
  }
  for (const v of extraValues) {
    if (Number.isFinite(v)) values.push(v);
  }

  const rawMin = values.length ? Math.min(...values) : 0;
  const rawMax = values.length ? Math.max(...values) : 1;
  const vPad = (rawMax - rawMin) * 0.08 || 1;
  const minV = rawMin - vPad;
  const maxV = rawMax + vPad;
  const spanV = maxV - minV || 1;

  const xForDate = (dateStr) => padLeft + ((parseYMD(dateStr) - minT) / spanT) * plotWidth;
  const yForValue = (v) => padTop + plotHeight - ((v - minV) / spanV) * plotHeight;
  const baselineY = padTop + plotHeight;

  return {
    xForDate,
    yForValue,
    baselineY,
    minT,
    maxT,
    minV,
    maxV,
    padLeft,
    padTop,
    padRight,
    padBottom,
    plotWidth,
    plotHeight,
  };
}

/** Catmull-Rom -> cubic Bezier smoothed path through `points` ([x, y] pairs). */
export function smoothPath(points) {
  if (points.length === 0) return "";
  if (points.length === 1) return `M${points[0][0]},${points[0][1]}`;
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i > 0 ? i - 1 : i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i < points.length - 2 ? i + 2 : i + 1];
    const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
    const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
    const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
    const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2[0]},${p2[1]}`;
  }
  return d;
}

/** A closed area path: the smoothed top edge, closed down to `baselineY`. */
export function buildAreaPath(points, baselineY) {
  if (points.length === 0) return "";
  const top = smoothPath(points);
  const lastX = points[points.length - 1][0];
  const firstX = points[0][0];
  return `${top} L${lastX},${baselineY} L${firstX},${baselineY} Z`;
}

/** Small circles at each raw data point (SVG markup string). */
export function renderScatterPoints(data, key, xForDate, yForValue, opts = {}) {
  const { radius = 2.5, className = "raw-pt" } = opts;
  return data
    .filter((d) => Number.isFinite(d[key]))
    .map(
      (d) =>
        `<circle class="${className}" cx="${xForDate(d.date)}" cy="${yForValue(d[key])}" r="${radius}"/>`
    )
    .join("");
}

/** A dashed horizontal reference line (e.g. goal weight) with a label. */
export function renderReferenceLine(valueKg, yForValue, width, padLeft, label, opts = {}) {
  const { className = "ref-line", labelClassName = "ref-label" } = opts;
  const y = yForValue(valueKg);
  return `
    <line class="${className}" x1="${padLeft}" x2="${width}" y1="${y}" y2="${y}"/>
    <text class="${labelClassName}" x="${width - 4}" y="${y - 4}" text-anchor="end">${label}</text>
  `;
}

/** Dashed vertical markers (e.g. milestones) with a dot at the top. */
export function renderMilestoneMarkers(milestones, xForDate, padTop, plotHeight, opts = {}) {
  const { lineClassName = "milestone-line", dotClassName = "milestone-dot" } = opts;
  return milestones
    .filter((m) => m.date)
    .map((m) => {
      const x = xForDate(m.date);
      return `
        <line class="${lineClassName}${m.reached ? " reached" : ""}" x1="${x}" x2="${x}" y1="${padTop}" y2="${padTop + plotHeight}"/>
        <circle class="${dotClassName}${m.reached ? " reached" : ""}" cx="${x}" cy="${padTop}" r="3"/>
      `;
    })
    .join("");
}

/** Simple vertical bars (e.g. calorie intake history), each optionally
 * colored by a per-bar CSS class from `classForValue(value)`. */
export function renderBars(data, key, xForDate, yForValue, baselineY, opts = {}) {
  const { barWidth = 6, classForValue = () => "bar" } = opts;
  return data
    .filter((d) => Number.isFinite(d[key]))
    .map((d) => {
      const x = xForDate(d.date) - barWidth / 2;
      const y = yForValue(d[key]);
      const h = Math.max(0, baselineY - y);
      return `<rect class="${classForValue(d[key])}" x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="2"/>`;
    })
    .join("");
}
