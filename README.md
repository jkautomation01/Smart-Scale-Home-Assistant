# Medisana BLE Scale for Home Assistant

A custom Home Assistant **integration** (not a Supervisor add-on) that talks
directly to a Medisana BS4xx-family Bluetooth smart scale — including the
**Medisana BS436** — over BLE, using whatever Bluetooth adapter or ESPHome
Bluetooth proxy you've already configured in Home Assistant.

## Why an integration and not an add-on

Add-ons run in their own isolated Docker container and don't share Home
Assistant's Bluetooth stack. Integrations run inside Home Assistant core and
can reuse the adapters/proxies already set up under **Settings → Devices &
Services → Bluetooth**. Since the goal was "use the Bluetooth adapter I've
already configured in Home Assistant," this is built as an integration.

## How it works

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
confirm BS430, BS440, BS444 and BS550. **The BS436 is not independently
confirmed** — it's very likely the same protocol family, but see
[Verifying your BS436](#verifying-your-bs436-or-troubleshooting) below before
trusting the numbers.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add this repository's URL, category "Integration".
3. Install "Medisana BLE Scale", then restart Home Assistant.

### Manual

Copy `custom_components/medisana_ble/` into your Home Assistant
`config/custom_components/` directory, then restart Home Assistant.

## Setup

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

## Verifying your BS436 (or troubleshooting)

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
or timestamps look wrong, most likely culprit is the epoch offset — toggle
"Scale clock uses 2010-01-01 epoch" in the integration's options.

If nothing ever shows up: the scale only advertises for a short window after
a weigh-in, and Home Assistant's Bluetooth proxy/adapter needs to be in
range *at that moment* — walk to the scale, weigh in, and check the log
within the next ~30 seconds.

## Credits

- Protocol reverse-engineering: [keptenkurk/BS440][bs440]
- ESPHome component this was requested to be based on:
  [bwynants/weegschaal][weegschaal]

[bs440]: https://github.com/keptenkurk/BS440
[weegschaal]: https://github.com/bwynants/weegschaal
[proxy]: https://esphome.io/components/bluetooth_proxy.html
