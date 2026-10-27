# Firmware configurator

A local web app that turns "I want these features" into a compiled, checksummed, flashable **Ender3S1-CFG** image for the Ender 3 S1 - using the same pinned Marlin tree, the same configuration and the same verification as the rest of this repository.

![Configurator UI](../../docs/img/configurator-ui.png)

## Quick start

```bash
./scripts/bootstrap.sh                      # once: pinned sources + PlatformIO 6.1.19
python3 tools/configurator/server.py        # -> http://127.0.0.1:8787
```

Three presets cover the common cases:

| Preset | What it selects |
|---|---|
| **What I run now** | exactly the feature set of the firmware on the machine today (the default state of the page) |
| **Minimum** | everything that can be turned off, turned off |
| **Add what fits** | starts from what you run now and adds every measured feature that still fits, cheapest first |

The page always shows whether the current selection is **bigger or smaller than the image you run now**, in bytes and percent, next to the flash bar.

## Using the page

* **Filter** at the top of the feature list matches names, ids and descriptions; group headers collapse when clicked, so 71 features stay navigable.
* **A build is tied to the selection it was made from.** Change a feature, the machine, the screen image or the asset pack and the write panel disables itself with *"the selection changed since that build"* - the card can no longer be written from a stale image. Change it back and it re-enables, because the signature matches again.
* **Errors surface as a toast** and in the log, never as a silent no-op: a refused build says why, a failed link says how many bytes overflowed, a refused write says which rule stopped it.
* **Modals** close on Escape, confirm on Enter, and return focus to where it was.
* The footer carries the date the costs were measured, so a stale catalogue is visible rather than implied.

## What a build gives you

| Artifact | What it is |
|---|---|
| `firmware.bin` | the image, stamped `Ender3S1-CFG` so `M115` identifies it |
| `manifest.json` | machine, selection, **what changed versus the shipped build**, warnings, predicted vs measured size, sha256, upstream commits |
| log | the full PlatformIO output |

## The screen

The panel is a second computer, and it is the one part of this machine whose firmware **cannot be built here**: its OS is a proprietary `.zlib` and its asset pack is a resource bundle, not code. Its menus are drawn from the mainboard's ProUI defines, which the feature list already controls - so a screen feature is a mainboard toggle, and this page handles it there.

What the configurator does control is the **pairing**: which OS image and which asset pack go on the screen's own card, chosen to match the firmware being built.

| OS image | Verified on this panel | Size | md5 | Note |
|---|---|---|---|---|
| Creality V3.1.9 (Two_C) | yes | 394,835 B | b99abe7a1388... | the image that revived this panel on 2026-07-29 |
| Creality V3.2.1 | no | 394,675 B | bd7d5f8d6aca... | newer official build, never flashed on this panel |

| Asset pack | Pairs with | Size | Bundled | Note |
|---|---|---|---|---|
| mriscoc DACAI assets | custom | 314,782 B | yes | the only pack that pairs with custom mainboard firmware; this is the one that works with this build |
| Creality V1.0.6_C assets | stock | 424,659 B | yes | pairs with the stock rollback image |
| Creality V3.1.9 assets | stock | 1,062,964 B | yes | the full official asset set for the V3.1.9 OS, accepted by this panel |
| Creality V3.2.1 assets (largest) | stock | 0 B | no (too large) | 3.48 MB: the panel rejected a 3.3 MB set with a 'max 1mb' error, so this one is documented but not shipped |

Both are bundled with the firmware: **Download bundle (.zip)** contains `firmware.bin`, `manifest.json`, `FLASH-THIS.txt` and `screen/firmware.zlib` plus `screen/private/` for the selected pair. A pack that does not pair with custom firmware is refused with the reason - that mismatch is what bricked this panel in July.

## Writing the card

The page can finish the job: pick the device, pick what goes on it, and the service formats it and copies the files.

* devices come from `lsblk` - only removable and loop devices are offered, internal disks are refused twice over (not removable, and any device carrying `/`, `/boot` or `/home`)
* a mounted card is unmounted first, and the modal names what is about to be destroyed
* the card is reformatted MBR + FAT32 with 4096-byte clusters, which is what the Creality bootloader needs
* one card can carry both: the mainboard image is renamed to an unused 8.3 name from the registry, and the screen OS plus `private/` go alongside it
* every copy is md5-compared after the write, and the filename is recorded in `firmware/flash-filenames.txt`
* writing needs root: the service uses passwordless sudo and refuses cleanly (409) instead of hanging on a password prompt

## Over-budget builds

A prediction is not a limit. If the selection is larger than the region, the build button turns red and reads the overflow, a line under it says what will happen, and a modal explains the trade-off before anything runs:

> Prediction: 234,728 B against the application region of 233,472 B - 1,256 B too large. On an STM32F103RCT6 with the 28 KiB bootloader the link will stop at 233,472 B. The build is still allowed because your board may have more flash than this preset assumes, or you may be checking what a configuration would need before trimming. The compiler is the authority here, not this estimate.

Build anyway and the linker answers: if the image really does not fit, the result says exactly how many bytes overflowed.

## Dependencies between features

Some toggles need another one to exist, and the service enforces both directions:

* `advk_tune_item` (the screen's linear-advance tuning screen) **requires** `linear_advance`. Ask for the screen item while LA is off and LA is switched back on for you, recorded as `auto_added` in the manifest.
* `plr` and its screen tune item move together, because Marlin's sanity check refuses one without the other.
* `restore_leveling_after_g28` and `enable_leveling_after_g28` are mutually exclusive; both selected is refused before a compiler starts.
* `bft` and `sdcard_readonly` conflict.

Every automatic change is written into the manifest, so a build never quietly differs from what you asked for.

## Every cost is measured

Nothing in the catalogue is a datasheet number. Each feature was priced by compiling it:

* a feature that is **on** in the shipped configuration was measured by turning it off and seeing how much the image shrank
* a feature that is **off** was measured by turning it on against a slimmed baseline that frees headroom, and seeing how much the image grew
* a link that overflows still measures: the linker states how many bytes over it went, and that becomes the price

Two baselines make that possible:

| Baseline | Flash | RAM | What it is |
|---|---|---|---|
| A | 232,312 B | 28,064 B | the shipped configuration, built by the configurator |
| B | 218,944 B | 25,812 B | A minus the screen extras, BFT and the macro slots, to make room for measuring additions |

The catalogue now holds **71 features** (48 on in your build, 23 off): **66 priced by a real build**, and 5 that cannot be toggled on this board at all (the compiler refuses them - see the list below). The most expensive things you are carrying:

| Feature | Cost |
|---|---|
| Cable flashing (binary file transfer) | +4688 B |
| MPC Autotune | +4224 B |
| Pidtempbed | +4048 B |
| Power-loss recovery | +3920 B |
| Linear advance | +3336 B |

### The five that cannot be toggled here

They are hidden from the page by default - a row you cannot touch is noise. Tick **Show options that cannot be used here** in the header and they reappear, greyed, with the compiler's reason next to each one. The same switch reveals the unsupported machine presets and the screen packs that pair with stock firmware, which are kept for the Ender 3 Pro work later on.

| Advanced Pause Feature | required by FILAMENT_RUNOUT_SCRIPT, which uses M600: it cannot be removed on its own |
| Nozzle Park Feature | required by ADVANCED_PAUSE_FEATURE, which is enabled: it cannot be removed on its own |
| Fan Soft Pwm | required by this board: disabling it fails the sanity check ('FAN_SOFT_PWM is required for your board') |
| Ccloud Print Support | does not compile on this tree: the cloud path needs print-stats globals that are configured out here |
| Sdcard Readonly | Marlin refuses this while power-loss recovery is on, and it also conflicts with cable flashing. It would be offered if both were off; today it is kept as a documented option, not a usable one. |

## The catalogue


### Motion and extrusion

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| Adaptive Step Smoothing | adaptive_step_smoothing | on | +208 B | +2756 B |
| Advanced Pause Feature | advanced_pause_feature | on | not toggleable | - |
| Arc Support | arc_support | on | +2960 B | +0 B |
| Babystep Display Total | babystep_display_total | off | +72 B | +4 B |
| Babystepping | babystepping | on | +1196 B | +8 B |
| Bezier Curve Support | bezier_curve_support | off | +1168 B | +0 B |
| Fan kickstart (100 ms) | fan_kickstart | on | +56 B | +4 B |
| Filament Load Unload Gcodes | filament_load_unload_gcodes | on | +728 B | +0 B |
| Fwretract | fwretract | on | +1856 B | +56 B |
| Input shaping on Z | is_z | on | +1636 B | +284 B |
| Input Shaping X | input_shaping_x | on | +1692 B | +2532 B |
| Input Shaping Y | input_shaping_y | on | +1692 B | +2532 B |
| Linear advance | linear_advance | on | +3336 B | +940 B |
| Live Z from the host (M293/M294) | ep_babystep | on | +160 B | +0 B |
| Non-linear extrusion (M592) | nle | on | +592 B | +28 B |
| Nozzle clean (G12) | nozzle_clean | on | +1400 B | +0 B |
| Nozzle Park Feature | nozzle_park_feature | on | not toggleable | - |
| Skew correction (M852) | skew | on | +1568 B | +12 B |
| Slowdown | slowdown | on | +64 B | +0 B |
| Smooth linear advance | smooth_la | on | +1280 B | +524 B |

### Leveling and probing

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| Bed Tramming Include Center | bed_tramming_include_center | off | +40 B | +0 B |
| Enable Leveling after G28 | enable_leveling_after_g28 | off | +8 B | +0 B |
| Extrapolate Beyond Grid | extrapolate_beyond_grid | off | +0 B | +0 B |
| High-speed probe mode | bltouch_hs | on | +368 B | +0 B |
| Multiple probing per point (2 + 1 extra) | probing_avg | on | +0 B | +0 B |
| Preheat before Leveling | preheat_before_leveling | on | +328 B | +0 B |
| Probe Offset Wizard | probe_offset_wizard | off | +0 B | +0 B |
| Restore Leveling after G28 | restore_leveling_after_g28 | off | +16 B | +0 B |
| Z Min Probe Repeatability Test | z_min_probe_repeatability_test | on | +2432 B | +0 B |

### Thermal

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| Fan Soft Pwm | fan_soft_pwm | on | not toggleable | - |
| Hotend Idle Timeout | hotend_idle_timeout | on | +1040 B | +16 B |
| MPC Autotune | mpc_autotune | on | +4224 B | +88 B |
| MPC autotune menu | mpc_autotune_menu | on | +24 B | +0 B |
| MPC PTC | mpc_ptc | on | +192 B | +8 B |
| Pidtempbed | pidtempbed | on | +4048 B | +48 B |

### Host and connectivity

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| 5 G-code macros in EEPROM | gcode_macros | on | +392 B | +256 B |
| Advanced Ok | advanced_ok | on | +128 B | +0 B |
| Auto Report Position | auto_report_position | off | +224 B | +8 B |
| Auto Report SD Status | auto_report_sd_status | off | +248 B | +12 B |
| Auto Report Temperatures | auto_report_temperatures | on | +312 B | +8 B |
| Cable flashing (binary file transfer) | bft | on | +4688 B | +880 B |
| Emergency Parser (careful) | emergency_parser | on | +696 B | +16 B |
| Host Action Commands | host_action_commands | on | +1936 B | +4 B |
| Host Prompt Support | host_prompt_support | on | +1600 B | +4 B |
| Host status notifications | host_notifications | on | +104 B | +0 B |
| Long Filename Host Support | long_filename_host_support | on | +480 B | +0 B |
| Sdcard Sort Alpha | sdcard_sort_alpha | on | +1240 B | +3324 B |

### Screen and UI

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| Activate Mesh Item | activate_mesh_item | off | +152 B | +0 B |
| Advk Tune Item | advk_tune_item | off | +32 B | +0 B |
| Ccloud Print Support | ccloud_print_support | off | not toggleable | - |
| Jd Tune Item | jd_tune_item | off | +32 B | +0 B |
| Mediasort Menu Item | mediasort_menu_item | off | +112 B | +0 B |
| No Blink Ind | no_blink_ind | off | +0 B | +0 B |
| Preview Menu Item | preview_menu_item | off | +0 B | +0 B |
| Screen: custom colour themes | ui_colors | on | +2080 B | +8 B |
| Screen: endstop diagnostics | ui_esdiag | on | +616 B | +0 B |
| Screen: G-code preview | ui_gcode_preview | on | +1696 B | +0 B |
| Screen: live temperature plot | ui_plot | on | +1376 B | +1040 B |
| Screen: lock screen | ui_lockscreen | on | +584 B | +4 B |
| Screen: toolbar | ui_toolbar | on | +1864 B | +60 B |
| Smooth Encoder Menuitems | smooth_encoder_menuitems | off | +40 B | +0 B |
| Zoffset Save Settings | zoffset_save_settings | off | +8 B | +0 B |

### Diagnostics

| Feature | Id | In your build | Flash | RAM |
|---|---|---|---|---|
| Config Export | config_export | off | +0 B | +0 B |
| Eeprom Auto Init | eeprom_auto_init | on | +0 B | +0 B |
| EEPROM chatter | eeprom_chitchat | off | +864 B | +0 B |
| Eeprom Init Now (careful) | eeprom_init_now | off | +96 B | +0 B |
| M503 settings dump | m503 | on | +1424 B | +0 B |
| Power-loss recovery | plr | on | +3920 B | +996 B |
| Print statistics (M78) | printcounter | on | +1816 B | +32 B |
| Sdcard Readonly (careful) | sdcard_readonly | off | not toggleable | - |
| Speaker | speaker | off | +192 B | +12 B |

## How it works

```text
features.json  ->  apply_features.py  ->  PlatformIO  ->  firmware.bin + manifest.json
      ^                  |                   ^
      |                  v                   |
   server.py  <-- budget check refuses over-budget selections
      ^
      |  HTTP + static page
   browser
```

| File | Role |
|---|---|
| `features.json` | the catalogue: every toggle, the defines it flips, the measured flash and RAM cost, the machines it applies to |
| `apply_features.py` | copies the baseline configuration, flips the defines, **verifies each flip landed**, stamps the identity, applies the upstream source patch, enforces the budget |
| `server.py` | stdlib HTTP service: catalogue, build queue, job status, log tail, artifact and manifest download |
| `web/` | the page: checkboxes, presets, live budget and size delta, build log, result panel |
| `measure.py` | the measurement harness that produced the costs above |
| `merge_measurements.py` | writes measured costs back into the catalogue |
| `validate_catalog.py` | static consistency check, part of `make verify` - proves every define exists exactly once and that `on_by_default` matches the configuration file |

## Verified

| Check | Result |
|---|---|
| Default selection | predicted 232,312 B, measured 232,312 B, error **0 B** |
| Two toggles off (`ui_colors` + `is_z`) | predicted 228,596 B, measured 228,596 B, error **0 B**, 3,748 B smaller than the running image |
| **Add what fits** (9 features added on top) | predicted 233,328 B including the 64 B/feature margin, measured 232,736 B: 592 B conservative, and it builds |
| Over-budget request | refused before compiling, with the exact overflow |
| Artifact identity | `M115` reports `Ender3S1-CFG` |
| Artifact integrity | `scripts/check-vector-table.py` passes on every build |
| Catalogue consistency | `validate_catalog.py`: no inconsistencies across all 71 features |

![A finished build: predicted equals measured](../../docs/img/configurator-result.png)

## Limits

* **STM32F103 only.** F401 boards take a different image with a different vector offset; the catalogue marks them unsupported rather than pretending.
* **This service runs a compiler.** It binds to `127.0.0.1` and has no authentication. Do not expose it to a network you do not control.
* **One job at a time**, queue depth 4. A cold tree is refused with a pointer to `./scripts/bootstrap.sh`.
* **Curated, not exhaustive.** Marlin has hundreds of options; the catalogue carries the ones that mean something on this machine. Adding another is one entry plus one measurement run.
* **Marginal costs.** Each price is the cost of that feature against the two baselines above; two features that share code can interact by a few bytes of alignment. The result panel always shows the exact measured size of the selection you built, so the prediction is a planning aid, not a promise.

## Serverless variant

[``.github/workflows/configurator.yml``](../../.github/workflows/configurator.yml) runs the same apply-and-build on GitHub Actions via `workflow_dispatch`. It is a template: not exercised on a runner yet, while the local path above has.

---

[<- Back to the project README](../../README.md)
