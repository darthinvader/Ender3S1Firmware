# Firmware configurator

A local web app that turns "I want these features" into a compiled, checksummed, flashable `Ender3S1-CFG` image for the Ender 3 S1 - using the same pinned Marlin tree, the same configuration and the same verification as the rest of this repository.

![Configurator UI](../../docs/img/configurator-ui.png)

## Why it exists

mriscoc's configurator writes `Configuration.h` for you, but it does not compile, does not tell you whether the result still fits in 233,472 bytes, and does not verify the artifact. MarlinWebBuild compiles, but only from stock example configs - there are no feature toggles. This does both, for this one machine, with the measured cost of every toggle.

## Quick start

```bash
# once: pinned sources + PlatformIO 6.1.19 in build/
./scripts/bootstrap.sh

# run the service
python3 tools/configurator/server.py
# -> http://127.0.0.1:8787
```

Pick features, watch the flash bar, press **Build firmware**. A build takes about 20 seconds on a warm tree and produces:

| Artifact | What it is |
|---|---|
| `firmware.bin` | the image, stamped `Ender3S1-CFG` so `M115` identifies it |
| `manifest.json` | machine, selection, predicted vs measured size, sha256, upstream commits |
| log | the full PlatformIO output |

## How it works

```text
features.json  ->  apply_features.py  ->  PlatformIO  ->  firmware.bin + manifest.json
   ^                    |                     ^
   |                    v                     |
 server.py  <---- budget check (refuses over-budget)  ----
   ^
   |  HTTP + static page
browser
```

| File | Role |
|---|---|
| `features.json` | the catalogue: every toggle, the `#define`s it flips, its measured flash and RAM cost, and which machines it applies to |
| `apply_features.py` | copies the baseline configuration, flips the defines, **verifies each flip landed**, stamps the identity, applies the upstream source patch, enforces the budget. Refuses to build a selection that cannot fit |
| `server.py` | stdlib HTTP service: catalogue, build queue, job status, log tail, artifact and manifest download |
| `web/` | the page: checkboxes, live budget bar, build log, measured-vs-predicted result |

One build runs at a time. PlatformIO owns the whole tree, so two concurrent compiles would corrupt it; requests queue instead.

## What is verified, and how

Measured on 2026-10-27 by driving the HTTP API, not by reading code:

| Check | Result |
|---|---|
| Default selection builds | predicted 232,312 B, measured **232,312 B**, error **0 B** |
| Two toggles off (ui_colors + is_z) | predicted 228,580 B, measured **228,596 B**, error **+16 B** (8 B of alignment interaction between the two, 16 B against the baseline) | predicted 228,580 B, measured 228,588 B, error **+8 B** (section-alignment interaction between the two features) |
| `ui_colors` off alone | saves **2,088 B** - was estimated at 1,200 B before calibration |
| `is_z` off alone | saves **1,644 B** - was estimated at 600 B |
| Artifact identity | `M115` reports `... Ender3S1-CFG (Oct 27 2026 ...)`, `MACHINE_TYPE:Ender3S1-CFG` |
| Over-budget request (EEPROM chatter enabled) | **refused before compiling**: "selection is 300 bytes over the 233472 byte application region" |
| Artifact integrity | `scripts/check-vector-table.py` passes: SP `0x2000BFD8`, reset `0x080092C5` |

Every other feature in the catalogue still carries an estimate - Marlin's own comment where it gives one, otherwise a symbol-table sum. The table above is how those estimates get replaced: build it, measure it, write the number down.


### The budget check earned its place immediately

The catalogue's first cost for `EEPROM_CHITCHAT` was a guess of 130 bytes. Turning it on overflowed the link by 300 bytes, so the real price is **1,460 bytes** - more than the 1,160 bytes the default selection leaves free. The predictor now refuses that selection before starting a compiler, and the measured number replaced the guess. Every remaining estimate in the catalogue is waiting for the same treatment.

## Limits worth knowing

* **STM32F103 only.** The F401 boards take a different image with a different vector offset; the catalogue marks them unsupported rather than pretending.
* **This service runs a compiler.** It binds to `127.0.0.1` by default and has no authentication. Do not expose it to a network you do not control.
* **One job at a time**, queue depth 4. A cold tree (no `build/`) is refused with a pointer to `./scripts/bootstrap.sh`.
* **Not exposed in the UI:** anything that is not a `#define` toggle. Mesh geometry, pin maps and the calibration values come from the baseline configuration and stay there.

## Serverless variant

[`.github/workflows/configurator.yml`](../../.github/workflows/configurator.yml) runs the same apply-and-build on GitHub Actions via `workflow_dispatch`, so a build can happen without any local service. It is a template: it has not been exercised on a runner yet, while the local path above has.

---

[<- Back to the project README](../../README.md)
