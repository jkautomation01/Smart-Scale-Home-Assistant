/*
 * Weight Milestones Card
 * A horizontal stepped row visualizing the Weight Coach `all_milestones`
 * list: reached milestones checked off, the next one highlighted, future
 * ones ghosted - each with its target weight and projected date.
 *
 * No build step required - plain ES module.
 *
 * ---------------------------------------------------------------------------
 * type: custom:weight-milestones-card
 * title: Milestones
 * next_milestone_entity: sensor.weight_coach_lose_next_milestone
 * ---------------------------------------------------------------------------
 */
import { HaFormCardEditor, entityField, textField } from "./lib/editor-helpers.js";

const DEFAULTS = { title: "Milestones" };

function fmtDate(dateStr) {
  if (!dateStr) return "–";
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

class WeightMilestonesCard extends HTMLElement {
  setConfig(config) {
    if (!config.next_milestone_entity) {
      throw new Error("weight-milestones-card: next_milestone_entity is required");
    }
    this._config = Object.assign({}, DEFAULTS, config);
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  getLayoutOptions() {
    return { grid_columns: 6, grid_rows: 3, grid_min_columns: 4 };
  }

  static getStubConfig() {
    return Object.assign({}, DEFAULTS);
  }

  static getConfigElement() {
    return document.createElement("weight-milestones-card-editor");
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const state = hass.states[cfg.next_milestone_entity];
    if (!state) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">Milestone entity not found</div></ha-card>`;
      return;
    }

    const milestones = state.attributes.all_milestones || [];
    const nextNumber = state.attributes.milestone_number;

    const stepsHtml = milestones
      .map((m) => {
        const isNext = m.number === nextNumber && !m.reached;
        const cls = m.reached ? "reached" : isNext ? "next" : "upcoming";
        const icon = m.reached ? "✓" : isNext ? "🚩" : m.number;
        return `
          <div class="step ${cls}">
            <div class="dot">${icon}</div>
            <div class="weight">${Number(m.weight_kg).toFixed(1)}</div>
            <div class="date">${m.reached ? "reached" : fmtDate(m.projected_date)}</div>
          </div>
        `;
      })
      .join(`<div class="connector"></div>`);

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; }
        .header { font-size:16px; font-weight:600; color:var(--primary-text-color); margin-bottom:14px; }
        .row { display:flex; align-items:center; }
        .step { display:flex; flex-direction:column; align-items:center; gap:4px; flex:0 0 auto; }
        .dot {
          width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center;
          font-size:14px; font-weight:700; color:var(--catppuccin-crust, #dce0e8);
          background: var(--catppuccin-overlay0, #9ca0b0);
        }
        .step.reached .dot { background: var(--catppuccin-green, #40a02b); }
        .step.next .dot { background: var(--catppuccin-mauve, #8839ef); box-shadow:0 0 0 4px rgba(var(--catppuccin-mauve-rgb, 136,57,239), .2); }
        .step.upcoming .dot { background: var(--catppuccin-surface2, #acb0be); color: var(--catppuccin-subtext0, #6c6f85); }
        .weight { font-size:12px; font-weight:600; color:var(--primary-text-color); }
        .date { font-size:10px; color:var(--secondary-text-color); }
        .step.next .weight { color: var(--catppuccin-mauve, #8839ef); }
        .connector { flex:1 1 auto; height:2px; background: var(--catppuccin-surface1, #bcc0cc); margin:0 2px 22px; min-width:8px; }
        .empty { padding:16px; color:var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">${cfg.title}</div>
        <div class="row">${stepsHtml}</div>
      </ha-card>
    `;
  }
}

class WeightMilestonesCardEditor extends HaFormCardEditor {
  get schema() {
    return [textField("title"), entityField("next_milestone_entity", "sensor", { required: true })];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        next_milestone_entity: "Next milestone sensor",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("weight-milestones-card-editor", WeightMilestonesCardEditor);
customElements.define("weight-milestones-card", WeightMilestonesCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "weight-milestones-card",
  name: "Weight Milestones",
  description: "A stepped row of your weight milestones - reached, next, and upcoming.",
});
