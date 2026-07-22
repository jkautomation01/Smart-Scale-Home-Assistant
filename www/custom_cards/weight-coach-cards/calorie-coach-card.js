/*
 * Calorie Coach Card
 * Active vs. suggested calorie target side by side, a badge showing
 * whether the suggestion comes from the BMR formula or your logged
 * intake, the days-until-checkin countdown, and an Accept button that
 * promotes the suggestion to active.
 *
 * No build step required - plain ES module.
 *
 * ---------------------------------------------------------------------------
 * type: custom:calorie-coach-card
 * title: Calorie Coach
 * tdee_entity: sensor.weight_coach_lose_tdee_estimate
 * active_target_entity: sensor.weight_coach_lose_active_calorie_target
 * suggested_target_entity: sensor.weight_coach_lose_suggested_calorie_target
 * days_until_checkin_entity: sensor.weight_coach_lose_days_until_check_in
 * accept_button_entity: button.weight_coach_lose_accept_suggested_target
 * ---------------------------------------------------------------------------
 */
import { HaFormCardEditor, entityField, textField } from "./lib/editor-helpers.js";

const DEFAULTS = { title: "Calorie Coach" };

function fmtKcal(v) {
  return Number.isFinite(v) ? Math.round(v).toLocaleString() : "–";
}

class CalorieCoachCard extends HTMLElement {
  setConfig(config) {
    if (!config.active_target_entity || !config.suggested_target_entity) {
      throw new Error("calorie-coach-card: active_target_entity and suggested_target_entity are required");
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
    return { grid_columns: 6, grid_rows: 4, grid_min_columns: 4 };
  }

  static getStubConfig() {
    return Object.assign({}, DEFAULTS);
  }

  static getConfigElement() {
    return document.createElement("calorie-coach-card-editor");
  }

  _acceptTarget() {
    const cfg = this._config;
    if (!this._hass || !cfg.accept_button_entity) return;
    this._hass.callService("button", "press", { entity_id: cfg.accept_button_entity });
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const activeState = hass.states[cfg.active_target_entity];
    const suggestedState = hass.states[cfg.suggested_target_entity];
    if (!activeState || !suggestedState) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">Calorie target entities not found</div></ha-card>`;
      return;
    }

    const tdeeState = cfg.tdee_entity ? hass.states[cfg.tdee_entity] : null;
    const checkinState = cfg.days_until_checkin_entity ? hass.states[cfg.days_until_checkin_entity] : null;

    const active = parseFloat(activeState.state);
    const suggested = parseFloat(suggestedState.state);
    const delta = Number.isFinite(active) && Number.isFinite(suggested) ? suggested - active : 0;
    const hasChange = Math.abs(delta) >= 1;

    const tdeeSource = suggestedState.attributes.tdee_source || (tdeeState && tdeeState.attributes.tdee_source);
    const sourcePill =
      tdeeSource === "logged_intake"
        ? `<div class="pill pill-green">📊 From your logged intake</div>`
        : `<div class="pill pill-blue">🧮 Formula estimate</div>`;

    let checkinHtml = "";
    if (checkinState) {
      const days = parseInt(checkinState.state, 10);
      const label = days === 0 ? "Check-in today" : days === 1 ? "Check-in tomorrow" : `Next check-in in ${days}d`;
      checkinHtml = `<div class="checkin">📅 ${label}</div>`;
    }

    const deltaHtml = hasChange
      ? `<div class="delta ${delta > 0 ? "up" : "down"}">${delta > 0 ? "▲" : "▼"} ${Math.abs(Math.round(delta))} kcal</div>`
      : `<div class="delta neutral">On target</div>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; display:flex; flex-direction:column; gap:12px; }
        .header { display:flex; justify-content:space-between; align-items:center; }
        .title { font-size:16px; font-weight:600; color:var(--primary-text-color); }
        .targets { display:flex; gap:12px; }
        .target-box { flex:1; border-radius:14px; padding:12px 14px; background:var(--secondary-background-color, rgba(127,127,127,.06)); }
        .target-box.suggested { background: rgba(var(--catppuccin-mauve-rgb, 136,57,239), .1); }
        .target-label { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--secondary-text-color); font-weight:600; }
        .target-value { font-size:26px; font-weight:800; color:var(--primary-text-color); margin-top:2px; }
        .target-value .unit { font-size:13px; font-weight:500; color:var(--secondary-text-color); }
        .meta-row { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }
        .pill { font-size:11px; font-weight:600; padding:4px 10px; border-radius:999px; }
        .pill-blue { background: rgba(var(--catppuccin-blue-rgb, 30,102,245), .12); color: var(--catppuccin-blue, #1e66f5); }
        .pill-green { background: rgba(var(--catppuccin-green-rgb, 64,160,43), .14); color: var(--catppuccin-green, #40a02b); }
        .checkin { font-size:12px; color:var(--secondary-text-color); }
        .delta { font-size:12px; font-weight:600; }
        .delta.up { color: var(--catppuccin-peach, #fe640b); }
        .delta.down { color: var(--catppuccin-sky, #04a5e5); }
        .delta.neutral { color: var(--catppuccin-green, #40a02b); }
        .accept-btn {
          border:none; border-radius:12px; padding:10px 16px; font-size:14px; font-weight:700;
          cursor:pointer; color:var(--catppuccin-crust, #fff);
          background: var(--catppuccin-mauve, #8839ef);
          transition: opacity .15s ease, transform .1s ease;
        }
        .accept-btn:disabled { background: var(--catppuccin-surface2, #acb0be); color: var(--catppuccin-subtext0, #6c6f85); cursor:default; }
        .accept-btn:not(:disabled):active { transform: scale(.98); }
        .empty { padding:16px; color:var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">
          <span class="title">${cfg.title}</span>
          ${deltaHtml}
        </div>
        <div class="targets">
          <div class="target-box active">
            <div class="target-label">Active</div>
            <div class="target-value">${fmtKcal(active)} <span class="unit">kcal</span></div>
          </div>
          <div class="target-box suggested">
            <div class="target-label">Suggested</div>
            <div class="target-value">${fmtKcal(suggested)} <span class="unit">kcal</span></div>
          </div>
        </div>
        <div class="meta-row">
          ${sourcePill}
          ${checkinHtml}
        </div>
        <button class="accept-btn" ${hasChange ? "" : "disabled"}>${hasChange ? "Accept suggested target" : "Already up to date"}</button>
      </ha-card>
    `;

    this.shadowRoot.querySelector(".accept-btn").addEventListener("click", () => this._acceptTarget());
  }
}

class CalorieCoachCardEditor extends HaFormCardEditor {
  get schema() {
    return [
      textField("title"),
      entityField("tdee_entity", "sensor"),
      entityField("active_target_entity", "sensor", { required: true }),
      entityField("suggested_target_entity", "sensor", { required: true }),
      entityField("days_until_checkin_entity", "sensor"),
      entityField("accept_button_entity", "button"),
    ];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        tdee_entity: "TDEE estimate sensor",
        active_target_entity: "Active calorie target sensor",
        suggested_target_entity: "Suggested calorie target sensor",
        days_until_checkin_entity: "Days-until-checkin sensor",
        accept_button_entity: "Accept-target button",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("calorie-coach-card-editor", CalorieCoachCardEditor);
customElements.define("calorie-coach-card", CalorieCoachCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "calorie-coach-card",
  name: "Calorie Coach",
  description: "Active vs. suggested calorie target, where the suggestion comes from, and a one-tap accept button.",
});
