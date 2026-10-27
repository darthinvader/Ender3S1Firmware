# Calibration: the tuned values and how they were measured

After the custom `Ender3S1-F1-v2` firmware was flashed on 2026-07-30 the machine was recalibrated end to end: extruder steps, probe offsets, motion limits, thermal models, input shaping, linear advance, the runout sensor and the UBL mesh. This page is the engineering record — the values that are in EEPROM now, the method behind each one, and the traps that cost time. Everything on this page lives in EEPROM, not in the firmware image; see [EEPROM, rollback and safety](#eeprom-rollback-and-safety).

The raw material is the two archived dumps:

- [calibration/eeprom-Ender3S1-F1-v2-20260730.txt](../calibration/eeprom-Ender3S1-F1-v2-20260730.txt) — full `M503` dump plus the 7×7 mesh topography, 2026-07-30
- [calibration/eeprom-20260729-uber-build.txt](../calibration/eeprom-20260729-uber-build.txt) — the previous (uber) build, for comparison

Where a dump disagrees with the tables below, the tables win. The dumps are snapshots, and the 2026-07-30 snapshot predates the final input-shaping sweep later that same day.

## Final values

| Parameter | Final value | Units | Set with |
| --- | --- | --- | --- |
| Extruder steps | 428 (stock firmware 424.9) | steps/mm | `M92 E428` |
| Probe X offset | -31.80 | mm | `M851 X-31.80` |
| Probe Y offset | -40.50 | mm | `M851 Y-40.50` |
| Probe Z offset | -3.10 | mm | `M851 Z-3.10` |
| Max acceleration X / Y | 5000 / 5000 | mm/s² | `M201 X5000 Y5000` |
| Print acceleration | 3000 | mm/s² | `M204 P3000` |
| Retract acceleration | 1500 | mm/s² | `M204 R1500` |
| Travel acceleration | 3000 | mm/s² | `M204 T3000` |
| Junction deviation | 0.02 | mm | `M205 J0.02` |
| Bed PID (P / I / D) | 83.18 / 15.04 / 306.76 | — | `M304 P83.18 I15.04 D306.76` |
| Hotend MPC heater power | 40.00 | W | `M306 E0 P40.00` |
| Hotend MPC block heat capacity | 13.24 | J/K | `M306 E0 C13.24` |
| Hotend MPC sensor responsiveness | 0.2164 | K/s per K | `M306 E0 R0.2164` |
| Hotend MPC ambient transfer, fan off | 0.0919 | W/K | `M306 E0 A0.0919` |
| Hotend MPC ambient transfer, fan full | 0.1053 | W/K | `M306 E0 F0.1053` |
| Hotend MPC filament heat capacity | 0.0056 | J/(K·mm) | `M306 E0 H0.0056` |
| Input shaping X | F48 · D0.08 | Hz · ratio | `M593 X F48 D0.08` |
| Input shaping Y | F48 · D0.08 | Hz · ratio | `M593 Y F48 D0.08` |
| Linear advance K | 0.08 | — | `M900 K0.08` |
| Smooth-LA time constant | 0.02 | s | `M900 U0.02` |
| Filament runout sensor | ON, debounce 200 | ms | `M412 S1 D200` |
| UBL mesh | 7×7, slot 0 active, probed at 60 °C | points | `G29 P1` / `G29 P3 R` / `G29 S0` |

Notes on the table:

- The bed PID terms are Marlin's bed PID set; the three numbers are only meaningful together, as one tuned model for this bed.
- The MPC coefficients in EEPROM differ from the compiled defaults in [configs/Ender3S1-F1-v2/Configuration.h](../configs/Ender3S1-F1-v2/Configuration.h) (C 14.40, R 0.2187, A 0.1257, F 0.1315). The EEPROM values are the ones this machine runs and the ones to restore.
- Two further values are reported by the 2026-07-30 dump and were not part of the calibration campaign: `M203 X500.00 Y500.00 Z10.00 E45.00` (max feedrate, mm/s) and `M205 B20000.00 S0.00 T0.00` (minimum segment time and minimum feedrates). Leave them as stored.

### What the archived dump gets wrong

The 2026-07-30 file shows the pre-final state in two places. Do not restore from it blindly:

| In the dump | Actual final value | Why |
| --- | --- | --- |
| `M593 X F55.00 D0.15`, `M593 Y F58.00 D0.15` | `M593 X F48`, `M593 Y F48`, `D0.08` | Dump taken before the final FFT-driven sweep; 48 Hz / D0.08 was saved later the same day |
| `M306 E0 P40.00 L0.0028 Q20.00 C13.24 R0.2164 Astart` (line cut, followed by `Watchdog Reset`) | `M306 E0 P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056` | The dump was interrupted by the watchdog mid-line; the complete value is in the 2026-07-29 dump and in EEPROM |

The 2026-07-29 uber-build dump is older still and additionally shows `M204 P1500.00`, `M203 X300.00 Y300.00 Z5.00 E25.00`, `M900 K0.08` without the `U` term, `M412 S0` (runout off), `M420 S0` (leveling off) and a 5×5 mesh footprint (`C29 ... ; 5x5`). All of these are superseded.

## Applying the settings from scratch

The order matters: motion and thermal values first, the mesh last, because the mesh must be probed with the final probe offset already stored. Run this block as a file, or line by line with the printer idle.

```gcode
; 1. reset to firmware defaults and commit the reset
M502
M500

; 2. motion
M92 E428
M201 X5000 Y5000
M204 P3000 R1500 T3000
M205 J0.02

; 3. probe offset (must be stored before probing the mesh)
M851 X-31.80 Y-40.50 Z-3.10

; 4. thermal
M304 P83.18 I15.04 D306.76
M306 E0 P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056

; 5. input shaping — the F token is mandatory on this build
M593 X F48 D0.08
M593 Y F48 D0.08

; 6. linear advance
M900 K0.08 U0.02

; 7. filament runout
M412 S1 D200

; 8. hot mesh: 7x7, saved to slot 0
M190 S60              ; probe hot, at print temperature
G28
G29 P1                ; probe every reachable point
G29 P3 R              ; fill missed points by interpolation
G29 A                 ; activate UBL
G29 S0                ; store to slot 0
M500                  ; persist everything

; 9. verify leveling is on
M420 S1
```

Points that are easy to get wrong:

- `M502` rewrites the RAM copy only. Without the following `M500` a power cycle returns the previous contents, and the rest of the sequence then builds on the wrong base.
- `M502` also clears the two settings that are not in the block above: the runout sensor reverts to disabled (hence `M412 S1` in step 7) and the mesh grid size reverts to the screen default. Verify **7×7 before step 8** — the grid size is a SCREEN setting stored in EEPROM (`meshSet`), not just a compile-time value, and a menu edit does not survive a reboot unless it is saved with `M500`. This is why early probes kept coming out 5×5.
- `M593` needs the `F` token. `M593 X48` is silently ignored on this build; set the axes with separate lines and confirm with a plain `M593` query. If a single combined `M593 X F48 Y F48 D0.08` line does not take, issue the two per-axis lines shown above.
- Probing runs `MULTIPLE_PROBING 2` with `EXTRA_PROBING 1` (compiled in), so each point is touched more than once and an outlying reading is discarded.
- After ANY bed-knob turn, re-probe: `G29 P1` → `G29 P3 R` → `G29 A` → `G29 S0` → `M500`. A stored mesh that no longer matches the plate is worse than no mesh.
- If leveling refuses to enable (`Error: Failed to enable Bed Leveling` — mesh dropped from RAM), recover with `G29 L0` → `G29 A` → `M500` and confirm with `M420 V`.

## Verifying without M503

`M503` dumps every settings block in one response, and on this build that dump is not safe: several `M503` runs ended in a `Watchdog Reset`, and the archived 2026-07-30 file shows it happening mid-`M306` line. A reset reinitializes the RAM copy, so any value set but not `M500`'d is gone — one watchdog reset wiped a freshly set input-shaping value four seconds before a test print started.

Verify one block at a time with its own query. Each of these reports only its own settings and does not trip the reset.

| Setting | Query | Must report |
| --- | --- | --- |
| Steps per unit | `M92` | `M92 X80.00 Y80.00 Z400.00 E428.00` |
| Max feedrate | `M203` | `M203 X500.00 Y500.00 Z10.00 E45.00` |
| Max acceleration | `M201` | `M201 X5000.00 Y5000.00 Z100.00 E1000.00` |
| Acceleration | `M204` | `M204 P3000.00 R1500.00 T3000.00` |
| Junction deviation | `M205` | `M205 B20000.00 S0.00 T0.00 J0.02` |
| Probe offset | `M851` | `M851 X-31.80 Y-40.50 Z-3.10 ; (mm)` |
| Bed PID | `M304` | `M304 P83.18 I15.04 D306.76` |
| Hotend MPC | `M306` | `M306 E0 P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056` |
| Input shaping | `M593` | Both axes at F48 with D0.08 — not F55/F58, not D0.15 |
| Linear advance | `M900` | `M900 K0.08 U0.02` |
| Filament runout | `M412` | `M412 S1 D200.00 ; Sensor ON` |
| Mesh / leveling | `M420 V` | `Bed Leveling ON`, `Active Mesh Slot 0`, a 7×7 grid |
| Mesh topography | `G29 T` | The `Bed Topography Report` grid and `Mesh is valid` |

Two habits follow from the watchdog quirk:

- Re-check `M593` with a plain query after every reconnect. A value that was live-set but never saved reverts on the next reset, and it is not visible in any other way.
- Save, then read back. Every value in the table above must survive a power cycle, and a query is the only proof that it did.

## Measurement methods

### Z offset: print evidence, not paper

Paper tests were not reliable on this machine. Walking the offset with paper got to `-2.62`, at which point the first layer stopped sticking — the paper said "correct" while the print said "too high". The accepted value came from judging actual first-layer prints: `-3.04` on 2026-07-29, raised to `-3.10` the same day after under-extruded-looking patches and thin lines on the first layer.

Rule: **trust print evidence over paper.** The paper test at the nozzle corners still has a job — verifying that the four corners of the plate are level relative to each other (see tramming below) — but it does not set the Z offset.

### Input shaping: photo FFT, not eyeball

An eyeball frequency sweep was too coarse: 55 Hz (X) and 58 Hz (Y) looked acceptable by eye and were saved. They were not the resonance.

1. Print an X/Y ringing test cube with the outer wall at 80 mm/s.
2. Photograph the cube faces and run a ringing-analysis script (photo FFT, `ringing_analyze.py` in the printer's benchmark tree — not part of this repository) over the ripple on each face.
3. Measured at 55/58 Hz: a dominant 1.65 mm ripple at 80 mm/s outer wall, on both axes.
4. 48 Hz removed that component on both axes. 48 Hz is the final frequency.
5. Damping then had to be corrected. With `D0.15` the frequency was right but a residual stayed at 48 Hz, because the shaper damping was far above the real belt damping. `D0.08` removed the 48 Hz component on both faces.

Residuals that remain and are accepted:

- **X at ~96 Hz** — the 2× harmonic of 48 Hz. Marlin's ZVD shaper cannot cancel a harmonic of the frequency it is shaping. Amplitude is low.
- **Y at ~62–66 Hz** — a second mechanical mode. Marlin's ZVD shapes one frequency per axis, so a second mode on the same axis cannot be shaped at the same time. This one is attacked mechanically, not in firmware.

Traps: the axes must be set with separate `M593 X F..` / `M593 Y F..` lines and the `F` token is mandatory; `M593` values are wiped by an unsaved reset; the compile-time defaults are `SHAPING_FREQ_X/Y 40.0` with `SHAPING_ZETA 0.15` in [configs/Ender3S1-F1-v2/Configuration_adv.h](../configs/Ender3S1-F1-v2/Configuration_adv.h), so an EEPROM reset also puts shaping back to the un-tuned 40 Hz / 0.15.

### Linear advance: K-factor pattern

A printed K-factor pattern (increasing K bands on one print) was judged by eye: the best rows were **8–9**, giving `K0.08`. The pattern is the method of record — no calculation, just the band with the sharpest corners and no bulging.

`U0.02` is the `SMOOTH_LIN_ADVANCE` time constant, added in the v2 build ([configs/Ender3S1-F1-v2/Configuration_adv.h](../configs/Ender3S1-F1-v2/Configuration_adv.h)). It is not part of classic linear advance: `M900 U0` reverts to classic LA if pressure behavior ever looks wrong, so the fallback is one command.

### Flow ceiling: stepped vase tower

The hotend's real limit was measured rather than assumed.

| Item | Value |
| --- | --- |
| Test object | Vase-mode tower, Ø40 × 40 mm, single wall |
| Line cross-section | 0.45 × 0.2 mm (= 0.09 mm²) |
| Temperature | 220 °C |
| Feedrate ramp | `M220` 100 % → 900 %, stepped +100 % every 5 mm |
| Resulting flow range | 1.8 → 16.2 mm³/s |

Verdict by eye, band by band:

| Band | Result |
| --- | --- |
| through ~9.0 mm³/s | glossy, clean |
| ~10.8 mm³/s | onset of matte / rough surface |
| ≥ 12.6 mm³/s | starved |

Consequence: extrusion speeds are capped to stay under the measured ceiling — extrusion 80, perimeter 100, infill 110, solid 100 mm/s (7.2–9.9 mm³/s). This is not cosmetic de-tuning; the stock Sprite hotend physically cannot melt 13 mm³/s, and requesting it produces weak infill and matte walls on large parts. Small prints never showed it because acceleration limits the achievable flow.

### Bed tramming: four G30 corner probes

Method (2026-10-01 session): UBL off, bed at 60 °C, four `G30` probes at `X30 Y30`, `X185 Y30`, `X30 Y175`, `X185 Y175`, two passes over all four to confirm repeatability (the two passes agreed within 0.018 mm).

| Pass | FL | FR | BL | BR | Spread |
| --- | --- | --- | --- | --- | --- |
| before | +0.109 | -0.140 | +0.156 | +0.124 | 0.293 mm |
| after | +0.090 | +0.059 | +0.074 | +0.092 | 0.033 mm |

Corrective moves were three knob turns on the front-right corner: ¼ turn the wrong way (-0.050 mm), one full turn back (+0.306 mm), then a ~1/5 turn nudge. That one full turn is the rate measurement.

Traps, all of which cost time:

- **Direction on this machine: CCW as seen from below = corner UP** (CW from below = down). The opposite of the usual Ender convention, and confirmed by a measured turn, not by recall. A direction that was "obviously right" from the top of the machine moved the corner the wrong way.
- **Rate is not a constant.** This session measured ~0.30 mm/turn at the corner; the earlier record said 0.44 mm/turn. Re-measure a known turn instead of trusting a stored rate.
- **`G30` X/Y is the PROBE position, not the nozzle position.** The firmware rejects a point whose nozzle would leave the bed (`Z Probe Past Bed`), so the reachable probe maximum is about X188 / Y179 with this offset.
- **Probe corners and paper corners are not the same points.** The probe sits 31.8 mm left and 40.5 mm behind the nozzle, so a mesh corner and a paper-test corner are roughly 45 mm apart and legitimately differ near the plate edges. The paper test decides the tram; the mesh compensates the inboard residual.
- **`C29` is off-limits.** Any parameter form of `C29` watchdog-resets this build. Mesh-inset changes must go through the screen's Mesh Settings menu (or a firmware rebuild), not through that command. EEPROM survived both crashed attempts.
- **The screen's mesh display is oriented back-to-front relative to the `G29 T` text report.** The text report's top row is the BACK of the bed; `(25,25)` is the physical front-left. A grid read backwards looks like a plate flipped in Y and sends you adjusting the wrong corner.

### Mesh and thermal models

The mesh is 7×7, stored in slot 0 and active, probed hot at 60 °C. The archived grid is that 2026-07-30 probe; the mesh has been rebuilt since (re-probed 2026-08-20, rebuilt again after the 2026-10-01 tram), so read the archived topography as a picture of the plate, not as the current mesh.

Thermal: the bed keeps PID (`M304`), the hotend does not — MPC replaces it (`M306`), with the PTC option compiled in so heater power tracks temperature. The bed PID numbers and the exact MPC tuning session are **not recorded** in the calibration notes; MPC autotune (`M306 T`) is compiled in and is the supported way to regenerate them. The filament heat capacity `H0.0056` matches the compiled 1.75 mm PLA value of `FILAMENT_HEAT_CAPACITY_PERMM`.

## What is still mechanical, not firmware

- **Plate bow.** The plate is not flat: the archived grid runs from -0.102 mm (row 0, column 3 — front-center dip) to +0.355 mm (row 5, column 6 — right-side hump). The mesh compensates it; firmware cannot remove it. A new mesh follows the plate wherever it bows.
- **Y second mechanical mode at ~62–66 Hz.** Marlin shapes one frequency per axis, so this cannot be fixed in firmware. The mechanical levers are Y belt tension (the twang test: a loose guitar string, not a drum) and the bed carriage eccentric nuts. The firmware-side fallback is lower outer-wall acceleration, not a second shaper.
- **Interpolated back-right mesh points.** The back-right points (recorded as `(6,7)`/`(7,6)` in the calibration notes) can miss their touch because the nozzle would need to be at X229.8 / Y219.5 against travel limits of 230 / 220 — a 0.2–0.5 mm margin, which is why the misses are intermittent. `G29 P3 R` fills them by interpolation and the mesh is then saved as valid. The clean fix is a mesh inset, blocked because `C29` watchdog-resets this build; until a firmware rebuild or a screen-side inset change, interpolated points are the accepted state.
- **Probe-versus-nozzle geometry.** The ~45 mm offset between probe points and paper-test corners is mechanical geometry, not a calibration error.

## EEPROM, rollback and safety

These values live in **EEPROM, not in the firmware image**. Consequences, in the order they bite:

- Reflashing the same firmware leaves EEPROM untouched, so a normal flash does not need this list re-applied. A full flash-reset, a wiped EEPROM, or a different build's EEPROM layout does — re-apply from the "Applying the settings from scratch" section.
- An EEPROM reset (`M502` + `M500`) resets more than the numbers in the table: the **filament runout sensor reverts to disabled** (`FIL_RUNOUT_ENABLED_DEFAULT false` in [configs/Ender3S1-F1-v2/Configuration.h](../configs/Ender3S1-F1-v2/Configuration.h) — the support is compiled in but off by default), the **mesh grid size reverts to the screen default** (verify 7×7 before probing), and **input shaping reverts to F40 / D0.15**. The runout sensor needs `M412 S1` plus `M500` after every reset, or a runout will not trigger.
- Anything set but not saved is lost on the next reset or power cycle. That includes a live `M593` during a tuning session. The apply sequence ends with `M500` for this reason, and the verify step exists to prove the save happened.
- Do not use `M503` for verification on this build (watchdog resets, section above). One query per setting.
- If the machine behaves as if the calibration vanished — wrong first layer, ghosting back, runout not triggering — check the single relevant query before re-tuning anything. The usual cause is an EEPROM reset or an unsaved value, not a failed calibration.
- Recovery references: this page for the values, and the two dumps in [calibration/](../calibration/) for the shape of a complete dump. To roll the firmware back, flash the rollback image from [firmware/](../firmware/) and then re-apply this list, because the older build's EEPROM contents are not implied by the newer ones.

[← Back to the project README](../README.md)
