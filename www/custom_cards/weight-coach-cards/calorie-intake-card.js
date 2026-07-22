/*
 * Calorie Intake Card
 * Quick-entry widget for today's total calorie intake, plus a small bar
 * chart of the last ~30 days (from the entity's `history` attribute),
 * bars colored by whether that day was over or under the active target.
 *
 * No build step required - plain ES module.
 *
 * ---------------------------------------------------------------------------
 * type: custom:calorie-intake-card
 * title: Calorie Intake
 * intake_entity: number.weight_coach_lose_calories_consumed_today
 * active_target_entity: sensor.weight_coach_lose_active_calorie_target
 * ---------------------------------------------------------------------------
 */
import { HaFormCardEditor, entityField, textField } from "./lib/editor-helpers.js";
import { computeGeometry, renderBars } from "./lib/svg-charts.js";

const DEFAULTS = { title: "Calorie Intake" };
const CHART_HEIGHT = 90;
const HISTORY_DAYS = 30;

class CalorieIntakeCard extends HTMLElement {
  setConfig(config) {
    if (!config.intake_entity) {
      throw new Error("calorie-intake-card: intake_entity is required");
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
    return 4;
  }

  getLayoutOptions() {
    return { grid_columns: 6, grid_rows: 4, grid_min_columns: 4 };
  }

  static getStubConfig() {
    return Object.assign({}, DEFAULTS);
  }

  static getConfigElement() {
    return document.createElement("calorie-intake-card-editor");
  }

  _logToday(value) {
    if (!this._hass || !Number.isFinite(value)) return;
    this._hass.callService("number", "set_value", { entity_id: this._config.intake_entity, value });
  }

  _render() {
    const cfg = this._config;
    const hass = this._hass;
    if (!hass || !cfg) return;

    const intakeState = hass.states[cfg.intake_entity];
    if (!intakeState) {
      this.shadowRoot.innerHTML = `<ha-card><div class="empty">Intake entity not found</div></ha-card>`;
      return;
    }

    const targetState = cfg.active_target_entity ? hass.states[cfg.active_target_entity] : null;
    const target = targetState ? parseFloat(targetState.state) : null;

    const todayValue = intakeState.state === "unknown" ? null : parseFloat(intakeState.state);
    const cutoff = Date.now() - HISTORY_DAYS * 86400000;
    const history = (intakeState.attributes.history || []).filter(
      (h) => new Date(`${h.date}T00:00:00`).getTime() >= cutoff
    );

    let chartHtml = "";
    if (history.length > 0) {
      const rawWidth = this.clientWidth;
      const width = rawWidth > 80 ? Math.round(rawWidth - 40) : 320;
      const height = CHART_HEIGHT;
      const geo = computeGeometry(history, {
        width,
        height,
        padTop: 4,
        padBottom: 4,
        padLeft: 4,
        padRight: 4,
        valueKeys: ["kcal"],
        extraValues: target !== null ? [target] : [],
      });
      const classForValue = (v) =>
        target !== null ? (v > target ? "bar bar-over" : "bar bar-under") : "bar bar-neutral";
      const bars = renderBars(history, "kcal", geo.xForDate, geo.yForValue, geo.baselineY, {
        barWidth: Math.max(2, Math.min(8, geo.plotWidth / history.length - 2)),
        classForValue,
      });
      chartHtml = `
        <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}">
          ${bars}
        </svg>
      `;
    } else {
      chartHtml = `<div class="empty-chart">No logged days yet</div>`;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        ha-card { height:100%; box-sizing:border-box; padding:16px 20px; display:flex; flex-direction:column; gap:10px; }
        .header { font-size:16px; font-weight:600; color:var(--primary-text-color); }
        .entry-row { display:flex; align-items:center; gap:8px; }
        .entry-input {
          flex:1; font-size:20px; font-weight:700; padding:8px 12px; border-radius:10px;
          border:1px solid var(--catppuccin-surface1, #bcc0cc); background:var(--card-background-color); color:var(--primary-text-color);
        }
        .entry-input:focus { outline:none; border-color: var(--catppuccin-mauve, #8839ef); }
        .log-btn {
          border:none; border-radius:10px; padding:10px 16px; font-size:14px; font-weight:700; cursor:pointer;
          background: var(--catppuccin-peach, #fe640b); color: var(--catppuccin-crust, #fff);
        }
        .log-btn:active { transform:scale(.97); }
        .hint { font-size:11px; color:var(--secondary-text-color); }
        .empty-chart { font-size:12px; color:var(--secondary-text-color); text-align:center; padding:20px 0; }
        .bar-over { fill: var(--catppuccin-peach, #fe640b); }
        .bar-under { fill: var(--catppuccin-green, #40a02b); }
        .bar-neutral { fill: var(--catppuccin-teal, #179299); }
        .empty { padding:16px; color:var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="header">${cfg.title}</div>
        <div class="entry-row">
          <input class="entry-input" type="number" step="10" min="0" placeholder="Today's calories" value="${todayValue ?? ""}"/>
          <button class="log-btn">Log</button>
        </div>
        <div class="hint">${target !== null ? `Target: ${Math.round(target)} kcal` : ""}</div>
        ${chartHtml}
      </ha-card>
    `;

    const input = this.shadowRoot.querySelector(".entry-input");
    this.shadowRoot.querySelector(".log-btn").addEventListener("click", () => {
      this._logToday(parseFloat(input.value));
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") this._logToday(parseFloat(input.value));
    });
  }
}

class CalorieIntakeCardEditor extends HaFormCardEditor {
  get schema() {
    return [
      textField("title"),
      entityField("intake_entity", "number", { required: true }),
      entityField("active_target_entity", "sensor"),
    ];
  }

  computeLabel(schema) {
    return (
      {
        title: "Title",
        intake_entity: "Calorie intake number",
        active_target_entity: "Active calorie target sensor",
      }[schema.name] || schema.name
    );
  }
}

customElements.define("calorie-intake-card-editor", CalorieIntakeCardEditor);
customElements.define("calorie-intake-card", CalorieIntakeCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "calorie-intake-card",
  name: "Calorie Intake",
  description: "Log today's calories in one tap, with a 30-day history bar chart colored by target.",
});
