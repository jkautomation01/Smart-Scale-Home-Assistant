/*
 * Weight Quick Actions Card
 * A compact "adjust your plan" control panel: goal weight, goal weekly
 * rate, activity level, and the manual weight-entry fallback (for when
 * the Bluetooth scale connection fails) - each editable in place.
 *
 * No build step required - plain ES module.
 *
 * ---------------------------------------------------------------------------
 * type: custom:weight-quick-actions-card
 * title: Adjust Your Plan
 * goal_weight_entity: number.weight_coach_lose_goal_weight
 * goal_rate_entity: number.weight_coach_lose_goal_weekly_rate
 * activity_level_entity: select.weight_coach_lose_activity_level
 * manual_weight_entity: number.weight_coach_lose_manual_weight_entry
 * ---------------------------------------------------------------------------
 */
import { HaFormCardEditor, entityField, textField } from "./lib/editor-helpers.js";

const DEFAULTS = { title: "Adjust Your Plan" };

function fmtLabel(v) {
  return v
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

class WeightQuickActionsCard extends HTMLElement {
  setConfig(config) {
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
    return document.createElement("weight-quick-actions-card-editor");
  }

  _setNumber(entityId, value) {
    if (!this._hass || !entityId || !Number.isFinite(value)) return;
    this._hass.callService("number", "set_value", { entity_id: entityId, value });
  }

  _setSelect(entityId, option) {
    if (!this._hass || !entityId || !option) return;
    this._hass.callService("select", "select_option", { entity_id: entityId, option });
  }

  _numberRow(entityId, label, icon, step) {
    const state = this._hass.states[entityId];
    if (!state) return "";
    const unit = state.attributes.unit_of_measurement || "";
    const value = state.state === "unknown" ? "" : state.state;
    return `
      <div class="row" data-entity="${entityId}" data-kind="number">
        <div class="row-label"><span class="icon">${icon}</span>${label}</div>
        <div class="row-control">
          <input class="num-input" type="number" step="${step}" value="${value}"/>
          <span class="unit">${unit}</span>
          <button class="save-btn">Set</button>
        </div>
      </div>
    `;
  }

  _selectRow(entityId, label, icon) {
    const state = this._hass.states[entityId];
    if (!state) return "";
    const options = state.attributes.options || [];
    const optionsHtml = options
      .map((o) => `<option value="${o}" ${o === state.state ? "selected" : ""}>${fmtLabel(o)}</option>`)
      .join("");
    return `
      <div class="row" data-entity="${entityId}" data-kind="select">
        <div class="row-label"><span class="icon">${icon}</span>${label}</div>
        <div class="row-control">
          <select class="sel-input">${optionsHtml}</select>
        </div>
      </div>
    `;
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const rows = [
      cfg.goal_weight_entity ? this._numberRow(cfg.goal_weight_entity, "Goal weight", "🎯", "0.1") : "",
      cfg.goal_rate_entity ? this._numberRow(cfg.goal_rate_entity, "Goal weekly rate", "📈", "0.05") : "",
      cfg.activity_level_entity ? this._selectRow(cfg.activity_level_entity, "Activity level", "🏃") : "",
      cfg.manual_weight_entity ? this._numberRow(cfg.manual_weight_entity, "Manual weigh-in", "✍️", "0.1") : "",
    ]
      .filter(Boolean)
      .join("");

    if (!rows) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">No entities configured</div></ha-card>`;
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; display:flex; flex-direction:column; gap:10px; }
        .header { font-size:16px; font-weight:600; color:var(--primary-text-color); margin-bottom:2px; }
        .row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:6px 0; border-top:1px solid var(--catppuccin-surface0, rgba(127,127,127,.12)); }
        .row:first-of-type { border-top:none; }
        .row-label { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; color:var(--primary-text-color); }
        .icon { font-size:15px; }
        .row-control { display:flex; align-items:center; gap:6px; }
        .num-input, .sel-input {
          font-size:14px; font-weight:600; padding:6px 8px; border-radius:8px; width:84px;
          border:1px solid var(--catppuccin-surface1, #bcc0cc); background:var(--card-background-color); color:var(--primary-text-color);
        }
        .sel-input { width:auto; min-width:120px; }
        .num-input:focus, .sel-input:focus { outline:none; border-color: var(--catppuccin-mauve, #8839ef); }
        .unit { font-size:11px; color:var(--secondary-text-color); min-width:20px; }
        .save-btn {
          border:none; border-radius:8px; padding:6px 10px; font-size:12px; font-weight:700; cursor:pointer;
          background: var(--catppuccin-mauve, #8839ef); color: var(--catppuccin-crust, #fff);
        }
        .save-btn:active { transform:scale(.96); }
        .empty { padding:16px; color:var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">${cfg.title}</div>
        ${rows}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".row").forEach((row) => {
      const entityId = row.dataset.entity;
      const kind = row.dataset.kind;
      if (kind === "number") {
        const input = row.querySelector(".num-input");
        const commit = () => this._setNumber(entityId, parseFloat(input.value));
        row.querySelector(".save-btn").addEventListener("click", commit);
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") commit();
        });
      } else if (kind === "select") {
        const select = row.querySelector(".sel-input");
        select.addEventListener("change", () => this._setSelect(entityId, select.value));
      }
    });
  }
}

class WeightQuickActionsCardEditor extends HaFormCardEditor {
  get schema() {
    return [
      textField("title"),
      entityField("goal_weight_entity", "number"),
      entityField("goal_rate_entity", "number"),
      entityField("activity_level_entity", "select"),
      entityField("manual_weight_entity", "number"),
    ];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        goal_weight_entity: "Goal weight number",
        goal_rate_entity: "Goal weekly rate number",
        activity_level_entity: "Activity level select",
        manual_weight_entity: "Manual weight entry number",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("weight-quick-actions-card-editor", WeightQuickActionsCardEditor);
customElements.define("weight-quick-actions-card", WeightQuickActionsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "weight-quick-actions-card",
  name: "Weight Quick Actions",
  description: "Adjust goal weight, pace, activity level, and log a manual weigh-in fallback.",
});
