/*
 * Weight Trend Chart Card
 * Smoothed trend line (with gradient fill) plotted against raw weigh-in
 * scatter points, a dashed goal-weight reference line, and dashed vertical
 * milestone markers. Reads the `history` attribute the Weight Coach
 * integration exposes on its trend-weight sensor.
 *
 * No build step required - plain ES module.
 *
 * ---------------------------------------------------------------------------
 * type: custom:weight-trend-chart-card
 * title: Weight Trend
 * trend_weight_entity: sensor.weight_coach_lose_trend_weight
 * goal_weight_entity: number.weight_coach_lose_goal_weight
 * next_milestone_entity: sensor.weight_coach_lose_next_milestone
 * days: 90
 * ---------------------------------------------------------------------------
 */
import { HaFormCardEditor, entityField, textField, selectField } from "./lib/editor-helpers.js";
import {
  computeGeometry,
  smoothPath,
  buildAreaPath,
  renderScatterPoints,
  renderReferenceLine,
  renderMilestoneMarkers,
} from "./lib/svg-charts.js";

const DEFAULTS = { title: "Weight Trend", days: "90" };
const CHART_HEIGHT = 240;

class WeightTrendChartCard extends HTMLElement {
  setConfig(config) {
    if (!config.trend_weight_entity) {
      throw new Error("weight-trend-chart-card: trend_weight_entity is required");
    }
    this._config = Object.assign({}, DEFAULTS, config);
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    if (!this._resizeObserver) {
      this._resizeObserver = new ResizeObserver(() => this._render());
      this._resizeObserver.observe(this);
    }
  }

  disconnectedCallback() {
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  getCardSize() {
    return 6;
  }

  getLayoutOptions() {
    return { grid_columns: "full", grid_rows: 6, grid_min_rows: 4 };
  }

  static getStubConfig() {
    return Object.assign({}, DEFAULTS);
  }

  static getConfigElement() {
    return document.createElement("weight-trend-chart-card-editor");
  }

  _styleBlock() {
    return `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; display:flex; flex-direction:column; }
        .header { display:flex; justify-content:space-between; align-items:baseline; font-size:16px; font-weight:600; color:var(--primary-text-color); margin-bottom:10px; }
        .range { font-size:12px; font-weight:500; color:var(--secondary-text-color); }
        .empty { padding:24px 0; text-align:center; color:var(--secondary-text-color); font-size:13px; }
        .grad-top { stop-color: rgb(var(--catppuccin-green-rgb, 64,160,43)); stop-opacity:.32; }
        .grad-bottom { stop-color: rgb(var(--catppuccin-green-rgb, 64,160,43)); stop-opacity:0; }
        .trend-line { stroke: var(--catppuccin-green, #40a02b); stroke-width:2.5; }
        .raw-pt { fill: var(--catppuccin-overlay1, #8c8fa1); opacity:.65; }
        .ref-line { stroke: var(--catppuccin-red, #d20f39); stroke-width:1; stroke-dasharray:4,3; }
        .ref-label { fill: var(--catppuccin-subtext1, #5c5f77); font-size:10px; }
        .milestone-line { stroke: var(--catppuccin-mauve, #8839ef); stroke-width:1; stroke-dasharray:2,2; opacity:.55; }
        .milestone-line.reached { stroke: var(--catppuccin-green, #40a02b); }
        .milestone-dot { fill: var(--catppuccin-mauve, #8839ef); }
        .milestone-dot.reached { fill: var(--catppuccin-green, #40a02b); }
        .legend { display:flex; flex-wrap:wrap; gap:14px; margin-top:8px; font-size:11px; color:var(--secondary-text-color); }
        .legend span { display:flex; align-items:center; gap:5px; }
        .dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
        .dot-raw { background: var(--catppuccin-overlay1, #8c8fa1); }
        .dot-trend { background: var(--catppuccin-green, #40a02b); }
        .dot-goal { background: var(--catppuccin-red, #d20f39); }
        .dot-milestone { background: var(--catppuccin-mauve, #8839ef); }
      </style>
    `;
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const trendState = hass.states[cfg.trend_weight_entity];
    if (!trendState) {
      this.shadowRoot.innerHTML = `${this._styleBlock()}<ha-card><div class="empty">Trend weight entity not found</div></ha-card>`;
      return;
    }

    const goalState = cfg.goal_weight_entity ? hass.states[cfg.goal_weight_entity] : null;
    const milestoneState = cfg.next_milestone_entity ? hass.states[cfg.next_milestone_entity] : null;
    const goal = goalState ? parseFloat(goalState.state) : null;
    const milestones = milestoneState
      ? (milestoneState.attributes.all_milestones || []).map((m) => ({
          date: m.projected_date,
          reached: m.reached,
        }))
      : [];

    const days = cfg.days || 90;
    const cutoff = Date.now() - days * 86400000;
    const history = (trendState.attributes.history || []).filter(
      (h) => new Date(`${h.date}T00:00:00`).getTime() >= cutoff
    );

    if (history.length === 0) {
      this.shadowRoot.innerHTML = `${this._styleBlock()}<ha-card><div class="header"><span>${cfg.title}</span></div><div class="empty">No weigh-ins in the last ${days} days yet</div></ha-card>`;
      return;
    }

    const rawWidth = this.clientWidth;
    const width = rawWidth > 80 ? Math.round(rawWidth - 40) : 560;
    const height = CHART_HEIGHT;

    const geo = computeGeometry(history, {
      width,
      height,
      valueKeys: ["raw_weight_kg", "trend_kg"],
      extraValues: goal !== null ? [goal] : [],
    });
    const trendPoints = history
      .filter((d) => Number.isFinite(d.trend_kg))
      .map((d) => [geo.xForDate(d.date), geo.yForValue(d.trend_kg)]);
    const trendLine = smoothPath(trendPoints);
    const area = buildAreaPath(trendPoints, geo.baselineY);
    const scatter = renderScatterPoints(history, "raw_weight_kg", geo.xForDate, geo.yForValue);
    const goalLine = goal !== null ? renderReferenceLine(goal, geo.yForValue, width, geo.padLeft, "Goal") : "";
    const milestoneMarks = renderMilestoneMarkers(milestones, geo.xForDate, geo.padTop, geo.plotHeight);

    this.shadowRoot.innerHTML = `
      ${this._styleBlock()}
      <ha-card>
        <div class="header">
          <span>${cfg.title}</span>
          <span class="range">last ${days}d</span>
        </div>
        <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" overflow="visible">
          <defs>
            <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop class="grad-top" offset="0%"/>
              <stop class="grad-bottom" offset="100%"/>
            </linearGradient>
          </defs>
          <path d="${area}" fill="url(#trend-fill)" stroke="none"/>
          ${goalLine}
          ${milestoneMarks}
          <path class="trend-line" d="${trendLine}" fill="none"/>
          ${scatter}
        </svg>
        <div class="legend">
          <span><i class="dot dot-raw"></i>Raw weigh-ins</span>
          <span><i class="dot dot-trend"></i>Trend</span>
          ${goal !== null ? `<span><i class="dot dot-goal"></i>Goal</span>` : ""}
          ${milestones.length ? `<span><i class="dot dot-milestone"></i>Milestones</span>` : ""}
        </div>
      </ha-card>
    `;
  }
}

class WeightTrendChartCardEditor extends HaFormCardEditor {
  get schema() {
    return [
      textField("title"),
      entityField("trend_weight_entity", "sensor", { required: true }),
      entityField("goal_weight_entity", "number"),
      entityField("next_milestone_entity", "sensor"),
      selectField("days", [
        { value: "30", label: "30 days" },
        { value: "90", label: "90 days" },
        { value: "180", label: "180 days" },
        { value: "365", label: "365 days" },
      ]),
    ];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        trend_weight_entity: "Trend weight sensor",
        goal_weight_entity: "Goal weight number",
        next_milestone_entity: "Next milestone sensor",
        days: "Time range",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("weight-trend-chart-card-editor", WeightTrendChartCardEditor);
customElements.define("weight-trend-chart-card", WeightTrendChartCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "weight-trend-chart-card",
  name: "Weight Trend Chart",
  description: "Smoothed trend line with gradient fill, raw weigh-ins, goal line and milestone markers.",
});
