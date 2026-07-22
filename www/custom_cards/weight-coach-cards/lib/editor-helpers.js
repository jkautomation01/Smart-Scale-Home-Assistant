/*
 * Shared GUI config-editor plumbing for the Weight Coach cards, built on
 * Home Assistant's own <ha-form> element so each card gets a real visual
 * editor (entity pickers, text fields, ...) instead of forcing YAML.
 *
 * Every card's editor extends HaFormCardEditor and only needs to provide
 * its own `schema` getter + `computeLabel()` - the ha-form wiring,
 * config-changed event dispatch, and re-render-on-hass-update are handled
 * once, here.
 */

/**
 * ha-form isn't guaranteed to be registered yet just because the main HA
 * frontend has loaded - it's normally pulled in by the generic card editor
 * chunk, but nothing has necessarily requested that chunk yet the first
 * time a user opens *this* card's editor. Force it via loadCardHelpers(),
 * which is Home Assistant's own documented way to pull in card/editor
 * building blocks on demand.
 */
export async function ensureHaFormLoaded() {
  if (customElements.get("ha-form")) return;
  const helpers = await window.loadCardHelpers();
  const stub = await helpers.createCardElement({ type: "entity", entity: "sun.sun" });
  if (stub.constructor.getConfigElement) {
    await stub.constructor.getConfigElement();
  }
  await customElements.whenDefined("ha-form");
}

/** Schema helper: an entity-picker field. */
export function entityField(name, domain, opts = {}) {
  const entitySelector = { domain };
  if (opts.deviceClass) entitySelector.device_class = opts.deviceClass;
  const field = { name, selector: { entity: entitySelector } };
  if (opts.required) field.required = true;
  return field;
}

/** Schema helper: a plain text field. */
export function textField(name) {
  return { name, selector: { text: {} } };
}

/** Schema helper: a dropdown/select field. */
export function selectField(name, options) {
  return { name, selector: { select: { options, mode: "dropdown" } } };
}

/** Base class every card's editor extends. */
export class HaFormCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  // Subclasses override both of these.
  get schema() {
    return [];
  }

  computeLabel(schemaEntry) {
    return schemaEntry.name;
  }

  async _render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    await ensureHaFormLoaded();

    let form = this.shadowRoot.querySelector("ha-form");
    if (!form) {
      this.shadowRoot.innerHTML = `<style>:host { display: block; padding: 8px 0; }</style>`;
      form = document.createElement("ha-form");
      form.addEventListener("value-changed", (ev) => this._valueChanged(ev));
      this.shadowRoot.appendChild(form);
    }

    form.hass = this._hass;
    form.data = this._config;
    form.schema = this.schema;
    form.computeLabel = (schemaEntry) => this.computeLabel(schemaEntry);
  }

  _valueChanged(ev) {
    ev.stopPropagation();
    const newConfig = ev.detail.value;
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }
}
