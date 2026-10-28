# Changelog

Firmware builds for a Creality Ender 3 S1 (STM32F103RCT6, mainboard v2.4.S1.301, DACAI screen) running mriscoc Professional Firmware. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); releases are dated by the day the build was flashed and verified on the machine, and the current one is tagged v2, and every artifact listed is the exact file kept in [firmware/](firmware/).

## Unreleased

No firmware image has been built or flashed since v2; the calibration work done afterwards is recorded under v2 because it changed EEPROM state, not the image. The entries below are the configurator, not the firmware on the machine.

### Added

- `scripts/configurator.sh`: one command that bootstraps on first use, starts the service, waits for it, opens the page, and stops on Ctrl+C.
- `make configurator`, the same thing.
- `scripts/selftest-configurator.py`: 14 behavioural checks against a live service, wired into `make verify`.
- Mesh size as a first-class control (3x3, 5x5, 7x7, 9x9 default) with the real ceiling documented: the runtime matrix is a fixed 9x9 because mriscoc ships ProUI precompiled.
- `docs/UI-NOTES.md`: every usability and accessibility rule the page follows, with its published source, and the gaps that remain.

### Fixed

- `/static/` and `/api/build/<id>` paths could walk out of their directory with `..` (now rejected with 404).
- `HEAD` requests returned 501.
- An exception inside a handler dropped the connection instead of answering with JSON 500.
- Request bodies were read without a size limit (now 64 KiB).
- The 9x9 mesh matrix had no build plumbing: `--mesh`, catalogue bounds, build request, signature and manifest now carry it.

## v2 - 2026-07-30

The current released build. Same Configurator selection as v1, plus the features and trims below; the machine name was changed so `M115` could confirm which image was actually running.

| Artifact | MD5 | Size |
| --- | --- | --- |
| [firmware/Ender3S1-F1-v2-20260730.bin](firmware/Ender3S1-F1-v2-20260730.bin) | `6e11c30095187fd50a62fa75904379f0` | 232972 B (app region usage 232344 B of 233472 B) |

Build: PlatformIO 6.1.19, env `STM32F103RC_creality`, flash 99.5% used (1128 B free), RAM 28064 B of 49152 B. Build log: [logs/build-Ender3S1-F1-v2.log](logs/build-Ender3S1-F1-v2.log). Recipe: [configs/recipes/Ender3S1-F1-v2.ini](configs/recipes/Ender3S1-F1-v2.ini).

### Added

- UBL mesh at 7x7 (49 points) instead of 5x5 (25 points).
- `INPUT_SHAPING_Z`, completing X/Y/Z shaping (compiled, then switched off at runtime with `M593 Z F0`).
- `SMOOTH_LIN_ADVANCE` (`ADVANCE_TAU 0.02`, exposed as `M900 U`).
- `MPC_PTC` in the MPC heater model, so cartridge power tracks its temperature (alpha 0.0028 at 20 °C reference).
- `BINARY_FILE_TRANSFER` + `CUSTOM_FIRMWARE_UPLOAD` re-enabled, so firmware can be uploaded over the cable (`M28 B1`) and installed on reboot.
- `GCODE_MACROS` + `GCODE_MACROS_IN_EEPROM`: 5 slots of 50 characters, `M810`–`M819`/`M820`, persisted.
- `HOST_STATUS_NOTIFICATIONS` for host-side state messages.
- `SKEW_CORRECTION` + `SKEW_CORRECTION_GCODE` (`M852`), identity factors until measured.
- `NONLINEAR_EXTRUSION` (`M592`), inert at `A=B=C=0`.
- `EP_BABYSTEPPING`, so `M293`/`M294` live Z works from the host.
- `NOZZLE_CLEAN_FEATURE` (`G12`).
- `FAN_KICKSTART_TIME 100`.
- `MULTIPLE_PROBING 2` + `EXTRA_PROBING 1` for probe averaging.
- `OPTIMIZED_MESH_STORAGE`, `BLTOUCH_HS_MODE` with extra clearance 0, `PROBING_FANS_OFF`, `DELAY_BEFORE_PROBING 200`.
- `BED_TRAMMING_USE_PROBE` with `BED_TRAMMING_PROBE_TOLERANCE 0.05` and the tramming wizard.
- Buffer increases: `BLOCK_BUFFER_SIZE` 16 to 32, `BUFSIZE` 16 to 32, `RX_BUFFER_SIZE` 512.

### Changed

- 2026-07-29: screen revived with the official V3.1.9 F401 OS plus mriscoc DACAI assets ([screen/](screen/)); bed trammed; Z offset moved to -3.10 on print evidence; restore point archived.
- `MPCTEMP` remains the hotend model; its constants come from autotune (`M306 E0 P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056`).
- `M593 X F48 D0.08` / `M593 Y F48 D0.08`: shaping frequency re-derived from photo FFT, replacing the X55/Y58 sweep. `M593 Z F0` leaves Z shaping off despite the compiled support.
- `M900 K0.08 U0.02`: Linear Advance K plus the smoothing time constant.
- `M205 J0.02`: junction deviation imposed. The Configurator's J0.1 corresponds to roughly classic jerk 24, far too aggressive for this machine.
- `M92 E428`, `M851 X-31.80 Y-40.50 Z-3.10`, `M201 X5000 Y5000`, `M204 P3000 R1500 T3000` saved to EEPROM.
- EEPROM trims: `EEPROM_CHITCHAT` and `EEPROM_INIT_NOW` disabled, reclaiming the 444 B overflow. Side effect: a flash no longer resets EEPROM, so calibration survives it; a deliberate `M502` + `M500` is the move when the settings layout changes.
- Slicer speeds capped to the measured flow ceiling (ext 80 / perim 100 / infill 110 / solid 100 mm/s, 7.2–9.9 mm³/s).
- Flashed over SD as `F1V2B30G.bin` and verified by `M115` (build of Jul 30, 16:04); BFT cable flashing was skipped at the time over a suspected SD fault that was later disproven.
- 2026-08-20: 7x7 UBL mesh re-probed hot at 60 °C and saved to slot 0; bed re-trammed and mechanically locked with printed bed locks. No firmware change.
- 2026-10-01: bed re-checked with four `G30` corner probes; spread reduced from 0.293 mm to 0.033 mm, mesh rebuilt (`G29 P1` → `P3 R` → `S0` → `M500`). No firmware change.

### Fixed

- Build failure from `MULTIPLE_PROBING` without `EXTRA_PROBING 1` (`SanityCheck.h:1599`, PROUI requirement).
- Build failure from the undefined `ICON_ShapingZ` symbol, fixed by the one-line source patch in [configs/patches/0002-proui-add-ICON_ShapingZ.patch](configs/patches/0002-proui-add-ICON_ShapingZ.patch).
- Flash overflow of 444 B, closed by the two EEPROM trims rather than by dropping a feature.

### Known issues

- An `M503` dump can trigger a watchdog reset. Settings are verified one at a time with their own query; a reset leaves EEPROM intact.
- Back-right mesh points (6,7) and (7,6) can come out NaN — the probe needs the nozzle at X229.8/Y219.5 against travel limits of 230/220. `G29 P3 R` fills them by interpolation; the 2026-10-01 mesh recorded (198,25) as an interpolated edge point.
- Y has a second mechanical mode around 62–66 Hz that ZVD shaping cannot cancel (one frequency per axis); it needs belt tension and carriage work, or lower outer-wall acceleration.
- Flow ceiling is ~9.0 mm³/s clean, onset ~10.8, bad from ~12.6 at 220 °C; slicer speeds are capped to stay under it.
- 1128 B of flash free — any further feature requires a trim first.
- `FIL_RUNOUT_ENABLED_DEFAULT` is false upstream; after any EEPROM reset the sensor must be re-enabled with `M412 S1` and `M500`.
- `INPUT_SHAPING_Z` is compiled but switched off at runtime; it is not a working Z-axis shaper until measured.
- A prime-line residue blob at the Z seam recurs, worked around by wiping the nozzle before a print; a G12 wipe in start G-code is the open follow-up.

## v1 - 2026-07-28

The first custom build: a Configurator selection of Ender3S1, 301F1, BLT, UBL, DACAI, T1, IS, LA, MPC, BFT, hand-edited for this machine.

| Artifact | MD5 | Size |
| --- | --- | --- |
| [firmware/Ender3S1-F1-UBL-IS-LA-MPC-BFT-20260728.bin](firmware/Ender3S1-F1-UBL-IS-LA-MPC-BFT-20260728.bin) | `8eaf6819abf118859e6d2923e572e252` | 226408 B |
| [firmware/upstream/Ender3S1-F1-UBL-MPC-20260106.bin](firmware/upstream/Ender3S1-F1-UBL-MPC-20260106.bin) (precompiled mriscoc, flashed first) | `1cf7006974f0e0b93745168da7626501` | 214800 B |

Build log: [logs/build-Ender3S1-F1-UBL-IS-LA-MPC-BFT.log](logs/build-Ender3S1-F1-UBL-IS-LA-MPC-BFT.log). Recipe: [configs/recipes/Ender3S1-F1-UBL-IS-LA-MPC-BFT.ini](configs/recipes/Ender3S1-F1-UBL-IS-LA-MPC-BFT.ini).

### Added

- UBL (`AUTO_BED_LEVELING_UBL`), replacing the stock mesh path, with `Z_SAFE_HOMING`, `MESH_INSET 38`, mesh bounds X10/Y10 to X195/Y175, and `OPTIMIZED_MESH_STORAGE`.
- Input shaping on X and Y (`M593`) with the shaping menu.
- Linear Advance (`M900`) with the compiled default left at `ADVANCE_K 0.0`.
- MPC hotend control (`MPCTEMP`) replacing `PIDTEMP`, with autotune support.
- Binary file transfer and custom firmware upload (`M28 B1`).
- BLTouch support: `BLTOUCH`, `USE_PROBE_FOR_Z_HOMING`, probe offset `{ -31.8, -40.5, 0 }`, `Z_PROBE_LOW_POINT -3`, deploy-probe clearance 5 mm, `M48` repeatability test.
- Bed tramming with the probe (`BED_TRAMMING_USE_PROBE`, tolerance 0.05 mm).
- Machine wiring corrected for the v301 board: `BOARD_CREALITY_V24S1_301`, `TEMP_SENSOR_0 1`, `E0_AUTO_FAN_PIN FAN1_PIN`, `DACAI_DISPLAY`, per-pin endstop pullups (Z min and probe kept), X/Y endstop hit state `LOW`, runout state `HIGH` with pulldown, `FILAMENT_RUNOUT_DISTANCE_MM 200`.
- Geometry: bed 220x220, `X_MIN_POS -10`, `Y_MIN_POS -8`, `X_MAX_POS 230`, `Y_MAX_POS 220`, `Z_MAX_POS 270`, park point `{X_MAX_POS - 2, Y_MAX_POS - 2, 20}`.
- Direct-drive default retract of 1 mm instead of the bowden 5 mm.

### Changed

- Replaced stock Creality Marlin V1.0.6_C with the mriscoc tree (`Ender3V2S1`, HEAD 2026-06-05) after first flashing a precompiled mriscoc image and verifying it over serial, with the vector table checked against the expected bootloader offset.
- Serial link now runs at 250000 baud.
- `S_CURVE_ACCELERATION` disabled in favour of junction deviation; `CLASSIC_JERK` stays off, so `M205` takes a `J` term.
- Machine identity: `MACHINE_NAME "Ender 3S1"` and a build-specific `CUSTOM_MACHINE_NAME` for `M115`.
- Compile-time E-steps default 424.9, superseded at runtime by `M92 E428`.

### Fixed

- Root-caused the repeated SD flash failures: the Creality bootloader skips a filename it has already flashed. `firmware.bin` had been reused on every attempt, so the file was ignored silently. Fixed by a short unique name per flash, tracked in [firmware/flash-filenames.txt](firmware/flash-filenames.txt).

### Known issues

- Screen still black and backlit; repair assets had been located but not yet applied.
- 5x5 UBL mesh only; no `INPUT_SHAPING_Z`, no macros, no smooth Linear Advance, no `M592`, no skew correction.
- `EEPROM_CHITCHAT`/`EEPROM_INIT_NOW` still enabled; the v2 feature set did not fit and needed the trims listed under v2.

## stock - before 2026-07-28

Creality's own Marlin V1.0.6_C (build date Jan 4 2022) on the same mainboard, as the machine arrived. Kept only as a rollback image.

| Artifact | MD5 | Size |
| --- | --- | --- |
| [firmware/stock/stock-V1.0.6_C-F103-rollback.bin](firmware/stock/stock-V1.0.6_C-F103-rollback.bin) | `fed5587ef885f3c123aec397d648bbcc` | 201652 B |

### Added

- Nothing in firmware terms; the machine was running stock Creality Marlin with a paper-verified Z offset and a stored mesh.
- Installed tooling: OctoPrint on the host, attached over USB serial.

### Changed

- 2026-07-27: mainboard SD slot cleaned and returned to service (`M21` → `SD card ok`, `M20` listing). The slot pins were visibly dirty; contact scrubbing fixed it.

### Fixed

- Factory-wiped EEPROM (Z offset 0) that produced `Failed to enable Bed Leveling`, `Invalid mesh` and `M112` emergency stops: a dummy 4x4 zero mesh was injected with `M421`, a real `G29` run and saved, and OctoPrint's disconnect-on-error disabled.
- Calibration recorded on stock: `M851 Z-3.00`, probe offsets `M851 X-31.80 Y-40.50`, a 16x16 `G29` mesh, hotend PID `M301 P18.97 I1.43 D62.74`, bed PID `M304 P83.18 I15.04 D306.76`, E-steps 424.9.

### Known issues

- Screen showed the boot logo with live values but no menu; it later went black and backlit after a mismatched screen-flash package.
- No Linear Advance, no input shaping, no UBL, no pressure or skew compensation — `M900` was an unknown command.
- Bed had a stable ~1.6 mm left-high/right-low tilt, compensated by the mesh; two mechanical repair attempts changed nothing.
- SD firmware flashing appeared dead: repeated attempts with a reused `firmware.bin` booted the old image every time. Later root-caused (see v1) to bootloader filename memory, not a missing bootloader.

[← Back to the project README](README.md)
