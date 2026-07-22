/*
 * Catppuccin color references for the Weight Coach cards.
 *
 * These are CSS custom properties defined by the "Catppuccin Auto Latte
 * Frappe" theme (themes/catppuccin/catppuccin.yaml), already installed and
 * applied elsewhere in this config. They're plain global custom properties,
 * so they cascade into a card's shadow DOM automatically - no per-card
 * theme detection needed, and light/dark (Latte/Frappé) switching is free.
 *
 * Every export includes a Catppuccin Latte hex fallback so cards still look
 * reasonably on-brand if this theme isn't the active one.
 *
 * One source of truth for "which color means what" across all six cards.
 */

// Raw color refs (`var(--catppuccin-X, #fallback)`), Latte hex fallbacks.
export const CTP = {
  rosewater: "var(--catppuccin-rosewater, #dc8a78)",
  flamingo: "var(--catppuccin-flamingo, #dd7878)",
  pink: "var(--catppuccin-pink, #ea76cb)",
  mauve: "var(--catppuccin-mauve, #8839ef)",
  red: "var(--catppuccin-red, #d20f39)",
  maroon: "var(--catppuccin-maroon, #e64553)",
  peach: "var(--catppuccin-peach, #fe640b)",
  yellow: "var(--catppuccin-yellow, #df8e1d)",
  green: "var(--catppuccin-green, #40a02b)",
  teal: "var(--catppuccin-teal, #179299)",
  sky: "var(--catppuccin-sky, #04a5e5)",
  sapphire: "var(--catppuccin-sapphire, #209fb5)",
  blue: "var(--catppuccin-blue, #1e66f5)",
  lavender: "var(--catppuccin-lavender, #7287fd)",
  text: "var(--catppuccin-text, #4c4f69)",
  subtext1: "var(--catppuccin-subtext1, #5c5f77)",
  subtext0: "var(--catppuccin-subtext0, #6c6f85)",
  overlay2: "var(--catppuccin-overlay2, #7c7f93)",
  overlay1: "var(--catppuccin-overlay1, #8c8fa1)",
  overlay0: "var(--catppuccin-overlay0, #9ca0b0)",
  surface2: "var(--catppuccin-surface2, #acb0be)",
  surface1: "var(--catppuccin-surface1, #bcc0cc)",
  surface0: "var(--catppuccin-surface0, #ccd0da)",
  base: "var(--catppuccin-base, #eff1f5)",
  mantle: "var(--catppuccin-mantle, #e6e9ef)",
  crust: "var(--catppuccin-crust, #dce0e8)",
};

// `-rgb` companions (bare "r, g, b" var references) for alpha-blended
// fills, e.g. `rgb(${CTP_RGB.green} / 0.35)` or an SVG gradient stop.
export const CTP_RGB = {
  rosewater: "var(--catppuccin-rosewater-rgb, 220, 138, 120)",
  flamingo: "var(--catppuccin-flamingo-rgb, 221, 120, 120)",
  pink: "var(--catppuccin-pink-rgb, 234, 118, 203)",
  mauve: "var(--catppuccin-mauve-rgb, 136, 57, 239)",
  red: "var(--catppuccin-red-rgb, 210, 15, 57)",
  maroon: "var(--catppuccin-maroon-rgb, 230, 69, 83)",
  peach: "var(--catppuccin-peach-rgb, 254, 100, 11)",
  yellow: "var(--catppuccin-yellow-rgb, 223, 142, 29)",
  green: "var(--catppuccin-green-rgb, 64, 160, 43)",
  teal: "var(--catppuccin-teal-rgb, 23, 146, 153)",
  sky: "var(--catppuccin-sky-rgb, 4, 165, 229)",
  sapphire: "var(--catppuccin-sapphire-rgb, 32, 159, 181)",
  blue: "var(--catppuccin-blue-rgb, 30, 102, 245)",
  lavender: "var(--catppuccin-lavender-rgb, 114, 135, 253)",
  overlay1: "var(--catppuccin-overlay1-rgb, 140, 143, 161)",
};

// Semantic roles used consistently across all six cards, so "what color is
// the goal line" etc. only has one answer, defined once.
export const ROLE = {
  accent: CTP.mauve, // primary accent: progress rings, active-state highlights
  trendLine: CTP.green, // the smoothed weight trend line + its area fill
  rawPoint: CTP.overlay1, // raw/unsmoothed scatter points
  goalLine: CTP.red, // goal-weight reference line
  milestone: CTP.mauve, // milestone markers
  milestoneReached: CTP.green,
  milestoneUpcoming: CTP.overlay0,
  calories: CTP.peach, // calorie/fire related accents
  water: CTP.teal,
  formula: CTP.sky, // tdee_source == "formula" pill
  loggedIntake: CTP.green, // tdee_source == "logged_intake" pill
  warning: CTP.yellow,
  danger: CTP.red,
};

export const ROLE_RGB = {
  trendLine: CTP_RGB.green,
  accent: CTP_RGB.mauve,
  calories: CTP_RGB.peach,
};
