/*
 * Weight Summary Card
 * The Weight Coach dashboard's hero tile: a circular progress ring
 * (start -> goal completion), the current trend weight, distance to goal,
 * a days-until-checkin badge, and the next milestone.
 *
 * No build step required - plain ES module, drop the folder in
 * /config/www/custom_cards/weight-coach-cards and add the file as a
 * Lovelace resource (type: module).
 *
 * ---------------------------------------------------------------------------
 * type: custom:weight-summary-card
 * title: Weight
 * trend_weight_entity: sensor.weight_coach_lose_trend_weight
 * goal_weight_entity: number.weight_coach_lose_goal_weight
 * next_milestone_entity: sensor.weight_coach_lose_next_milestone
 * days_until_checkin_entity: sensor.weight_coach_lose_days_until_check_in
 * ---------------------------------------------------------------------------
 */
import { CTP } from "./lib/palette.js";
import { HaFormCardEditor, entityField, textField } from "./lib/editor-helpers.js";

const DEFAULTS = { title: "Weight" };

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

function fmt1(v) {
  return Number.isFinite(v) ? v.toFixed(1) : "–";
}

class WeightSummaryCard extends HTMLElement {
  setConfig(config) {
    if (!config.trend_weight_entity) {
      throw new Error("weight-summary-card: trend_weight_entity is required");
    }
    this._config = Object.assign({}, DEFAULTS, config);
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  getLayoutOptions() {
    return {
      grid_columns: "full",
      grid_rows: 4,
      grid_min_columns: 6,
      grid_min_rows: 3,
    };
  }

  static getStubConfig() {
    return Object.assign({}, DEFAULTS);
  }

  static getConfigElement() {
    return document.createElement("weight-summary-card-editor");
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const trendState = hass.states[cfg.trend_weight_entity];
    const goalState = cfg.goal_weight_entity ? hass.states[cfg.goal_weight_entity] : null;
    const milestoneState = cfg.next_milestone_entity ? hass.states[cfg.next_milestone_entity] : null;
    const checkinState = cfg.days_until_checkin_entity ? hass.states[cfg.days_until_checkin_entity] : null;

    if (!trendState) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">Trend weight entity not found</div></ha-card>`;
      return;
    }

    const current = parseFloat(trendState.state);
    const unit = trendState.attributes.unit_of_measurement || "kg";
    const history = trendState.attributes.history || [];
    const startWeight = Number.isFinite(history[0]?.raw_weight_kg) ? history[0].raw_weight_kg : current;
    const goal = goalState ? parseFloat(goalState.state) : null;

    let ringHtml;
    let toGoHtml;
    const maintaining = goal !== null && Math.abs(goal - startWeight) < 0.05;

    if (goal !== null && Number.isFinite(goal) && !maintaining) {
      const fraction = clamp01((startWeight - current) / (startWeight - goal));
      const pct = Math.round(fraction * 100);
      const r = 54;
      const circumference = 2 * Math.PI * r;
      const dash = circumference * fraction;
      ringHtml = `
        <svg class="ring" viewBox="0 0 128 128">
          <circle class="ring-track" cx="64" cy="64" r="${r}"/>
          <circle class="ring-progress" cx="64" cy="64" r="${r}"
            stroke-dasharray="${dash} ${circumference}"
            transform="rotate(-90 64 64)"/>
          <text class="ring-pct" x="64" y="58" text-anchor="middle">${pct}%</text>
          <text class="ring-label" x="64" y="76" text-anchor="middle">to goal</text>
        </svg>
      `;
      const remaining = Math.abs(current - goal);
      toGoHtml = `<div class="to-go">${fmt1(remaining)} ${unit} to go</div>`;
    } else {
      ringHtml = `
        <svg class="ring" viewBox="0 0 128 128">
          <circle class="ring-track" cx="64" cy="64" r="54"/>
          <text class="ring-pct" x="64" y="58" text-anchor="middle">🎯</text>
          <text class="ring-label" x="64" y="76" text-anchor="middle">maintaining</text>
        </svg>
      `;
      toGoHtml = `<div class="to-go">Holding steady</div>`;
    }

    let milestoneHtml = "";
    if (milestoneState) {
      const reached = milestoneState.attributes.reached;
      const date = milestoneState.attributes.projected_date;
      if (reached) {
        milestoneHtml = `<div class="chip chip-reached">🎉 Goal reached</div>`;
      } else {
        const weight = fmt1(parseFloat(milestoneState.state));
        const dateStr = date ? new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "–";
        milestoneHtml = `<div class="chip">🚩 Next: ${weight} ${unit} · ${dateStr}</div>`;
      }
    }

    let checkinHtml = "";
    if (checkinState) {
      const days = parseInt(checkinState.state, 10);
      const label = days === 0 ? "Check-in today" : days === 1 ? "Check-in tomorrow" : `Check-in in ${days} days`;
      checkinHtml = `<div class="chip chip-muted">📅 ${label}</div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; display:flex; align-items:center; gap:20px; }
        .title { font-size:14px; font-weight:600; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.04em; }
        .ring-wrap { flex:0 0 auto; }
        .ring { width:112px; height:112px; }
        .ring-track { fill:none; stroke:${CTP.surface1}; stroke-width:10; }
        .ring-progress { fill:none; stroke:${CTP.mauve}; stroke-width:10; stroke-linecap:round; transition:stroke-dasharray .6s ease; }
        .ring-pct { font-size:22px; font-weight:700; fill:var(--primary-text-color); }
        .ring-label { font-size:10px; fill:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.03em; }
        .main { display:flex; flex-direction:column; gap:6px; min-width:0; flex:1; }
        .weight-row { display:flex; align-items:baseline; gap:6px; }
        .weight-value { font-size:40px; font-weight:800; color:var(--primary-text-color); line-height:1; }
        .weight-unit { font-size:16px; color:var(--secondary-text-color); }
        .to-go { font-size:14px; color:var(--secondary-text-color); }
        .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
        .chip { font-size:12px; font-weight:600; padding:4px 10px; border-radius:999px; background:rgba(var(--catppuccin-mauve-rgb, 136,57,239), .12); color:${CTP.mauve}; }
        .chip-reached { background:rgba(var(--catppuccin-green-rgb, 64,160,43), .14); color:${CTP.green}; }
        .chip-muted { background:var(--secondary-background-color, rgba(127,127,127,.08)); color:var(--secondary-text-color); }
        .empty { padding:16px; color:var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="ring-wrap">${ringHtml}</div>
        <div class="main">
          <div class="title">${cfg.title}</div>
          <div class="weight-row">
            <span class="weight-value">${fmt1(current)}</span>
            <span class="weight-unit">${unit}</span>
          </div>
          ${toGoHtml}
          <div class="chips">${milestoneHtml}${checkinHtml}</div>
        </div>
      </ha-card>
    `;
  }
}

class WeightSummaryCardEditor extends HaFormCardEditor {
  get schema() {
    return [
      textField("title"),
      entityField("trend_weight_entity", "sensor", { required: true }),
      entityField("goal_weight_entity", "number"),
      entityField("next_milestone_entity", "sensor"),
      entityField("days_until_checkin_entity", "sensor"),
    ];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        trend_weight_entity: "Trend weight sensor",
        goal_weight_entity: "Goal weight number",
        next_milestone_entity: "Next milestone sensor",
        days_until_checkin_entity: "Days-until-checkin sensor",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("weight-summary-card-editor", WeightSummaryCardEditor);
customElements.define("weight-summary-card", WeightSummaryCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "weight-summary-card",
  name: "Weight Summary",
  description: "Hero tile: progress ring toward your goal, current trend weight, next milestone and check-in countdown.",
});
