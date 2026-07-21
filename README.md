# Smart Scale + Weight Coach for Home Assistant

Two custom Home Assistant **integrations** (not Supervisor add-ons):

- **[Medisana BLE Scale](#medisana-ble-scale)** — talks directly to a
  Medisana BS4xx-family Bluetooth smart scale over BLE, using whatever
  Bluetooth adapter or ESPHome Bluetooth proxy you've already configured in
  Home Assistant.
- **[Weight Coach](#weight-coach)** — a weight-loss/maintenance/gain coach
  built on top of any weight sensor (defaults to the Medisana one above, but
  works with any `device_class: weight` sensor): trend smoothing, milestones,
  and a suggested daily-calorie target that adapts over time.

They're deliberately separate: the scale driver stays a simple, stable data
source, and the coach is reusable with any weight sensor.

> **HACS note**: this repo has two `custom_components/` folders (one per
> integration above). HACS's "Integration" category is generally built
> around one integration per repository, so a HACS custom-repository add may
> only reliably discover/install one of them, or need to be added twice.
> Manual installation (copy the folder you want into
> `config/custom_components/`) always works for either one regardless.

## Medisana BLE Scale

Connects to a Medisana BS4xx-family scale — including the **Medisana
BS436** — over BLE.

### Why an integration and not an add-on

Add-ons run in their own isolated Docker container and don't share Home
Assistant's Bluetooth stack. Integrations run inside Home Assistant core and
can reuse the adapters/proxies already set up under **Settings → Devices &
Services → Bluetooth**. Since the goal was "use the Bluetooth adapter I've
already configured in Home Assistant," this is built as an integration.

### How it works

The scale doesn't stream data continuously — it wakes up and advertises over
BLE for a short window right after someone weighs in. This integration:

1. Registers a passive listener with Home Assistant's `bluetooth` integration
   for the scale's address (no extra scanning, no extra radio use).
2. When an advertisement is seen, it opens a GATT connection through
   whichever adapter/proxy Home Assistant used to see that advertisement.
3. Writes the current time to the scale (some models expect this), then
   reads back the weight, body-composition, and profile-slot notifications
   the scale sends for the person who just weighed in.
4. Updates sensors and disconnects.

The protocol itself (characteristic UUIDs, byte layouts) is not officially
documented by Medisana. It comes from the [keptenkurk/BS440][bs440] reverse
engineering project, which [bwynants/weegschaal][weegschaal] (the repo this
was requested from) also builds on for its ESPHome component. Both projects
confirm BS430, BS440, BS444 and BS550. **The BS436 has now been confirmed
working** against a real device — weight and body-composition readings
match what the scale itself shows. One protocol difference from
BS410/BS444: the **BS436 does not use the 2010-01-01 clock offset** —
leave "Scale clock uses 2010-01-01 epoch" turned **off** in the
integration's options, or the `measured_at` attribute will show a date
decades in the future.

### Installation

**HACS (custom repository)**: HACS → Integrations → ⋮ → Custom repositories
→ add this repository's URL, category "Integration" → install "Medisana BLE
Scale" → restart Home Assistant.

**Manual**: copy `custom_components/medisana_ble/` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

### Setup

1. Make sure a Bluetooth adapter (or an [ESPHome Bluetooth proxy][proxy]) is
   already configured under **Settings → Devices & Services → Bluetooth**,
   and that it's in range of the scale.
2. Weigh in once so the scale advertises, then go to **Settings → Devices &
   Services → Add Integration → Medisana BLE Scale**. If Home Assistant
   already spotted the advertisement you'll get a discovery confirmation
   prompt; otherwise pick it from the list of recently-seen Bluetooth
   devices, or type its MAC address in manually.
   - The MAC address can also be read with any generic BLE scanner app, or
     from Home Assistant's Bluetooth device list if it's ever been seen.
3. Open the integration's **Configure** options and map the scale's
   built-in user slots (1-8 — these are the profiles you set up with
   height/age/gender/activity level *on the scale itself*, which is also
   where the body-composition math is computed) to names. A slot with no
   name configured is ignored; you'll see a log warning if someone weighs in
   on an unmapped slot as a reminder to add it.
4. Each named slot gets sensors: **Weight**, **Body Fat %**, **Body Water
   %**, **Muscle Mass %**, **Bone Mass**, **Metabolic Rate (kcal)**. Gender,
   age, height and activity level (as configured on the scale) are exposed
   as attributes on the Weight sensor.
5. On a **BS436**, turn **off** "Scale clock uses 2010-01-01 epoch" in the
   same options dialog (it's on by default for the wider BS4xx family, but
   the BS436 uses a plain Unix timestamp — leaving it on shows the
   `measured_at` attribute 40 years in the future).
6. New entities aren't added to any dashboard automatically. Find them under
   **Settings → Devices & Services → Medisana BLE Scale**, or search for the
   scale's title (e.g. "BS436") in **Settings → Entities**, then add them to
   a dashboard/area as you would any other sensor.

### Troubleshooting

Turn on debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.medisana_ble: debug
```

Weigh in, then check the logs for `Weight payload`, `Body payload`, and
`Person payload` hex dumps. A sane weight payload starts with `1d`, a body
payload with `6f`, and a person payload with `84` — if you see those marker
bytes and the resulting `Weight`/`Body Fat`/etc. sensor values in Home
Assistant roughly match what the scale itself displays, the protocol is
confirmed compatible. If the numbers are off by a large, consistent factor,
or the `measured_at` attribute looks decades off, toggle "Scale clock uses
2010-01-01 epoch" in the integration's options (see the BS436 note above).

If nothing ever shows up: the scale only advertises for a short window after
a weigh-in, and Home Assistant's Bluetooth proxy/adapter needs to be in
range *at that moment* — walk to the scale, weigh in, and check the log
within the next ~30 seconds. Also double check you're actually looking at
the right entities (see step 6 above) — a successful reading updates the
sensors silently, it doesn't notify you.

## Weight Coach

A weight-loss/maintenance/gain coach layered on top of any weight sensor.
One config entry per coached person.

### What it does

- **Trend weight**: daily readings are noisy (water, food, sodium), so goals
  are tracked against a smoothed trend line (continuous-time exponential
  moving average, ~7-day time constant), not the raw daily number.
- **Actual weekly rate + projected end date**: a 21-day trailing regression
  of the trend line gives a real rate of change, projected forward to when
  you'll hit your goal weight.
- **Milestones**: your start→goal change is split into equal steps (4 by
  default), each with its own projected date, so progress feels concrete
  instead of one distant end date.
- **Suggested daily calorie target**: starts from a BMR (Mifflin-St Jeor,
  using your current trend weight) × activity-level TDEE estimate, sized to
  your goal rate. Two tiers, so it never breaks if you skip logging:
  - **With enough logged calorie-intake days** (10+ of the last 21 - doesn't
    need to be every day): back-calculates your *real* TDEE from the
    energy-balance identity (intake vs. actual trend change), which is more
    accurate than any formula.
  - **Otherwise**: falls back to comparing your actual trend rate against
    your goal rate and nudges the formula-based target accordingly. This is
    the always-available path - zero logged days still gets you sane advice.
  - Either way, a suggestion never auto-applies. Press **Accept Suggested
    Target** to make it the active target; that's also what the next
    recalibration is measured against.
- **Manual weight entry**: if the automatic weight sensor doesn't update for
  any reason (BLE connection failure, out of range, etc.), there's a
  fallback number entity that feeds the exact same trend/history pipeline.

### Installation

Same as above: HACS custom repository, or copy
`custom_components/weight_coach/` into `config/custom_components/`, then
restart Home Assistant.

### Setup

1. **Settings → Devices & Services → Add Integration → Weight Coach**.
2. Pick the weight sensor to coach against (any `device_class: weight`
   sensor - e.g. one of the Medisana BLE Scale sensors above).
3. Confirm sex/age/height - prefilled automatically if the source sensor
   already reports them (the Medisana integration's Weight sensor does, as
   attributes).
4. Pick a goal type (lose/maintain/gain), goal weight, target weekly rate,
   and how many milestones to split the journey into.
5. Pick an activity level (prefilled with a guess if the source sensor
   reports one, always adjustable).

### Entities

| Entity | What it's for |
|---|---|
| `number.*_goal_weight` | Your target weight - editable any time |
| `number.*_goal_weekly_rate` | Target pace (kg/week; negative = losing) |
| `number.*_calories_consumed_today` | Log today's total calorie intake once, at day's end |
| `number.*_manual_weight_entry` | Fallback weigh-in entry if the automatic sensor doesn't update |
| `select.*_activity_level` | Sedentary → very active, drives the TDEE estimate |
| `sensor.*_trend_weight` | Smoothed weight trend |
| `sensor.*_actual_weekly_rate` | Real rate of change from the last ~3 weeks |
| `sensor.*_projected_end_date` | Projected date to reach your goal weight |
| `sensor.*_next_milestone` | Next unreached milestone weight (full list + dates in attributes) |
| `sensor.*_tdee_estimate` | Current TDEE estimate (`tdee_source` attribute shows formula vs. logged-intake) |
| `sensor.*_active_calorie_target` | The calorie target you're currently following |
| `sensor.*_suggested_calorie_target` | What the coach currently recommends - press the button to adopt it |
| `button.*_accept_suggested_target` | Promotes the suggested target to active |

### Notes

- Trend/rate/projection/milestone sensors read "unavailable" for the first
  few days - there isn't enough history yet for a reliable trend or slope.
  That's expected.
- The two-tier calorie system is intentionally forgiving: skip logging
  intake for a week and nothing breaks, it just keeps using the
  outcome-based fallback until enough days are logged again.
- History (readings, intake, and the calorie-target adjustment log) is
  stored in Home Assistant's own storage, not the recorder - so it survives
  regardless of your recorder retention settings.

## Credits

- Medisana BLE protocol reverse-engineering: [keptenkurk/BS440][bs440]
- ESPHome component the Medisana integration was requested to be based on:
  [bwynants/weegschaal][weegschaal]

[bs440]: https://github.com/keptenkurk/BS440
[weegschaal]: https://github.com/bwynants/weegschaal
[proxy]: https://esphome.io/components/bluetooth_proxy.html
