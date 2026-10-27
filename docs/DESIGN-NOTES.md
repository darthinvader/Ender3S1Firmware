# Design notes: what was enabled, what was rejected, and why

This is the engineering record for the Marlin build that runs on the Ender 3 S1 in this repo: an STM32F103RCT6 board (Creality v2.4.S1.301) with 256 KB of flash, a 28 KiB SD bootloader, 48 KiB of RAM and no FPU. Flash and RAM are finite, and every feature in the table below is paid for out of the same 233472-byte application region. That single constraint decided almost every choice in this document: what is enabled, what was trimmed to make room, and what was refused outright.

| Budget | Total | Used | Free | Utilisation |
| --- | --- | --- | --- | --- |
| Flash application region | 233472 B | 232344 B | 1128 B | 99.5% |
| RAM | 49152 B | 28064 B | 21088 B | 57.1% |

The application link sits above a 28 KiB bootloader at `0x08007000`; the shipped image's vector table was checked against the previous build and matches (SP `0x2000BFD8`, all 63 vectors inside `0x08007000`–`0x08047000`). Flash is the binding constraint here, not RAM: there is about 21 KB of RAM spare and roughly one kilobyte of flash.

## Enabled features

The build is generated from the mriscoc Professional Firmware Configurator (recipe: [configs/recipes/Ender3S1-F1-v2.ini](../configs/recipes/Ender3S1-F1-v2.ini)), then hand-edited. The full machine-specific delta against the upstream Ender3S1 preset is in [configs/patches/0001-machine-configs.patch](../configs/patches/0001-machine-configs.patch), which carries the per-line rationale.

### Probing and leveling

| Feature | What it does | Why it is on this machine |
| --- | --- | --- |
| `AUTO_BED_LEVELING_UBL` | Mesh leveling with named slots, `G29`/`M420` control | The plate is not flat (front-centre dip, mid-right hump) and UBL gives slot storage plus the `G29 P1`/`P3 R`/`S0` workflow used here |
| `GRID_MAX_POINTS_X 7` (7x7) | 49 probed points instead of 25 | Cuts the spacing between probed points by about a third (four intervals per axis become six), so interpolation error over the plate bow shrinks; costs probing time, not flash |
| `MULTIPLE_PROBING 2` + `EXTRA_PROBING 1` | Fast probe then a slow re-probe, averaged | Corner checks repeat to about ±0.02 mm; averaging is cheaper than a better probe mount |
| `MESH_INSET 38` + `MESH_MIN_X/Y 10`, `MESH_MAX_X 195`, `MESH_MAX_Y 175` | Clamp the mesh to the reachable area | The probe sits 31.8 mm left and 40.5 mm in front of the nozzle, so a full-bed mesh would demand nozzle positions off the bed |
| `OPTIMIZED_MESH_STORAGE` | Store mesh points at reduced precision | Keeps a 7x7 mesh affordable in EEPROM |
| `BLTOUCH_HS_MODE true`, `BLTOUCH_HS_EXTRA_CLEARANCE 0` | High-speed probe deployment, no extra clearance term | Probing dominates `G29` wall time; the extra clearance was not needed on this machine |
| `PROBING_FANS_OFF` + `DELAY_BEFORE_PROBING 200` | Fan off and a 200 ms settle before each probe | Fan vibration and airflow move the trigger point |
| `Z_SAFE_HOMING` | Home Z at bed centre, and only when XY is known | Avoids homing onto a clip or the bed edge |
| `BED_TRAMMING_USE_PROBE` + `BED_TRAMMING_PROBE_TOLERANCE 0.05` + `HAS_TRAMMING_WIZARD 1` | Probe-based corner tramming with an on-screen wizard | A paper test cannot reach the probe's corners; the probe measures the same points the mesh uses, to 0.05 mm |
| `Z_MIN_PROBE_REPEATABILITY_TEST` | `M48` probe repeatability test | The only way to tell a bad mesh from a loose probe mount |
| `Z_PROBE_LOW_POINT -3` | Allow the probe to travel below the trigger point | Keeps a low trigger point from aborting the probe |
| `PREHEAT_BEFORE_LEVELING` (`LEVELING_NOZZLE_TEMP 0`, bed 50 °C) | Heat the bed before leveling, not the nozzle | Compensates bed expansion without oozing filament onto the bed; a BLTouch needs nothing from the nozzle |

### Motion and extrusion

| Feature | What it does | Why it is on this machine |
| --- | --- | --- |
| `LIN_ADVANCE` | `M900 K` pressure compensation | Direct-drive Sprite, measured `K0.08`; without it corners bulge at the accelerations this machine uses |
| `SMOOTH_LIN_ADVANCE` | Ramp pressure instead of stepping it (`ADVANCE_TAU`, exposed as `M900 U`) | Removes Linear Advance's acceleration ceiling; `M900 U0` reverts to classic behaviour if a print looks wrong |
| Default `ADVANCE_K 0.0` | Linear Advance is inert at boot | The compiled default is deliberately zero so a `M502` cannot resurrect an untuned K; the real value lives in EEPROM |
| `NONLINEAR_EXTRUSION` | `M592 A/B/C` correction for back-pressure under-extrusion | Targets the weak infill seen approaching the flow ceiling; ships at `A=B=C=0`, i.e. no-op until calibrated |
| `INPUT_SHAPING_X`/`_Y` + `SHAPING_MENU` | ZVD input shaping tuned with `M593` | Ringing measured at 48 Hz on both axes by photo FFT; damping 0.08 matches the real belt damping |
| `INPUT_SHAPING_Z` | Same shaping model on Z | Compiled for completeness, then disabled at runtime with `M593 Z F0` — no vertical ringing was measured worth shaping |
| `BABYSTEPPING` + `EP_BABYSTEPPING` + `BABYSTEP_ZPROBE_OFFSET` | `M293`/`M294` live Z from the host, writing through to the probe offset | Z offset is trimmed from OctoPrint mid-print; one number, not two that disagree |
| `RETRACT_LENGTH 1` | 1 mm default retract | The Sprite is direct drive; the upstream 5 mm is a bowden default and would chew filament |
| `FAN_KICKSTART_TIME 100` | 100 ms full-power pulse before PWM | The part fan will not start reliably at low duty otherwise |
| `NOZZLE_CLEAN_FEATURE` | `G12` wipe routine | Clears ooze and prime-line residue; stroke and point defaults kept |
| `SKEW_CORRECTION` + `SKEW_CORRECTION_GCODE` | `M852` skew correction | Identity factors until a skew test is run, so it costs nothing now and needs no rebuild later |

### Temperature control

| Feature | What it does | Why it is on this machine |
| --- | --- | --- |
| `MPCTEMP` (replaces `PIDTEMP`) | Predictive heater model instead of a PID loop | Upstream's own comments price PIDTEMP at ~4.1 K of flash against ~1.8 K for MPC without autotune; the modern model is also the affordable one on a 256 KB part |
| `MPC_PTC` | Model heater power as temperature-dependent | The Sprite uses a PTC cartridge; resistance, and therefore power, rises with temperature. Default `MPC_HEATER_ALPHA 0.0028` at 20 °C reference |
| `MPC_EDIT_MENU` + `MPC_AUTOTUNE_MENU` | Screen access to MPC constants and `M306` autotune | Tuning from the screen without a host cable; ~1.3 K + ~350 B per upstream's comments |
| `PIDTEMPBED` | Classic PID on the bed heater | The bed is slow and well-behaved; MPC on a second heater buys nothing |

### Host, storage and interface

| Feature | What it does | Why it is on this machine |
| --- | --- | --- |
| `BINARY_FILE_TRANSFER` + `CUSTOM_FIRMWARE_UPLOAD` | `M28 B1` binary upload and reboot-to-install | Cable flashing from OctoPrint's Firmware Updater. The upstream 301F1 board definition disables BFT for flash space, so a local `BFT.json` re-enables it last (see [configs/features/BFT.json](../configs/features/BFT.json)) |
| `GCODE_MACROS` + `GCODE_MACROS_IN_EEPROM` | 5 slots of 50 characters, `M810`–`M819`/`M820` | Short repeatable sequences that survive a power cycle |
| `HOST_STATUS_NOTIFICATIONS` | Push status messages to the host | OctoPrint learns about state changes instead of polling for them |
| `EEPROM_SETTINGS` | `M500`/`M501` persistence | The whole calibration below lives here; without it every flash is a full retune |
| `BLOCK_BUFFER_SIZE 32`, `BUFSIZE 32`, `RX_BUFFER_SIZE 512` | Deeper planner and serial buffers than the 16/16/64 defaults | Sustained throughput over a 250000-baud link; buffer starvation shows up as stutter and corner artefacts, not as an error |

### Board and machine wiring

| Setting | Value | Why |
| --- | --- | --- |
| `MOTHERBOARD` | `BOARD_CREALITY_V24S1_301` | The board is a v2.4.S1.301; the upstream default in this tree is the v4.2.2 pin map |
| `TEMP_SENSOR_0` | `1` | Stock Sprite thermistor. The `TEMP_SENSOR_0 13` variant is a different thermistor and reads wrong here |
| `E0_AUTO_FAN_PIN` | `FAN1_PIN` | The v301 routes the hotend fan to FAN1 |
| `ENDSTOPPULLUPS` | Disabled, with `ENDSTOPPULLUP_ZMIN` and `ENDSTOPPULLUP_ZMIN_PROBE` enabled individually | X/Y endstops are driven by the v301 board, so pullups are set per pin instead of globally; Z min and the probe input keep theirs |
| `X_MIN`/`Y_MIN_ENDSTOP_HIT_STATE` | `LOW` | v301 endstop wiring is active-low; the upstream default is `HIGH` |
| `FIL_RUNOUT_STATE` | `HIGH` + `FIL_RUNOUT_PULLDOWN` | v301 runout input idle state; the sensor exists on this machine and is switched on at runtime with `M412 S1` |
| `NOZZLE_TO_PROBE_OFFSET` | `{ -31.8, -40.5, 0 }` | Measured probe position; the Z component stays 0 so the offset lives in EEPROM |
| `USE_PROBE_FOR_Z_HOMING` | Enabled | CR Touch on the BLTouch port homes Z; the upstream manual-mesh preset homed on the Z endstop |
| `X_BED_SIZE`/`Y_BED_SIZE` | 220 / 220 | Physical bed |
| `X_MIN_POS`/`Y_MIN_POS`, `X_MAX_POS`/`Y_MAX_POS` | `-10`/`-8`, `230`/`220` | Travel is deliberately larger than the bed so the probe can reach the mesh borders |
| `Z_MAX_POS` | 270 | Machine height |
| `NOZZLE_PARK_POINT` | `{ X_MAX_POS - 2, Y_MAX_POS - 2, 20 }` | Park inside travel; the upstream point parked at `X_BED_SIZE + 10` |
| `DEFAULT_AXIS_STEPS_PER_UNIT` | E = 424.9 | Compile-time default only; the calibrated runtime value is `M92 E428` in EEPROM |
| `MACHINE_NAME` / `CUSTOM_MACHINE_NAME` | `"Ender 3S1"` / `"Ender3S1-F1-v2"` | `M115` is how a flash is verified here, by reading back the build identity |
| `DACAI_DISPLAY` | Enabled | Stock S1 colour screen |

### Where the tuned values live

None of these are compiled in; they are EEPROM state, set with the listed command and saved with `M500`.

| Value | Setting | Command |
| --- | --- | --- |
| Input shaping X/Y | 48 Hz, damping 0.08 | `M593 X F48 D0.08` / `M593 Y F48 D0.08` |
| Input shaping Z | disabled | `M593 Z F0` |
| Linear Advance | K 0.08, tau 0.02 | `M900 K0.08 U0.02` |
| Junction deviation | 0.02 mm | `M205 J0.02` |
| Hotend MPC | P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056 | `M306 E0 P40.00 C13.24 R0.2164 A0.0919 F0.1053 H0.0056` |
| Bed PID | P83.18 I15.04 D306.76 | `M304 P83.18 I15.04 D306.76` |
| Probe offset | X-31.80 Y-40.50 Z-3.10 | `M851 X-31.80 Y-40.50 Z-3.10` |
| E-steps | 428 | `M92 E428` |
| Acceleration / limits | `M201 X5000 Y5000`, `M204 P3000 R1500 T3000` | `M201`, `M204` |

## What was traded away

The first link of the build overflowed the application region by 444 bytes. Two flags closed the gap, and nothing else was cut:

| Trim | Flash reclaimed | What it actually costs |
| --- | --- | --- |
| `EEPROM_CHITCHAT` disabled | part of the 444 B | `M500`/`M501`/`M503` stop narrating what they did; errors are still reported |
| `EEPROM_INIT_NOW` disabled | part of the 444 B | A new build no longer resets EEPROM on first boot |

That second trade is the one that looks like a loss and is not. With `EEPROM_INIT_NOW` on, every flash wipes calibration and mesh; with it off, a flash keeps the previous build's EEPROM. The documented consequence is that a settings-layout change (v2 added macro slots to EEPROM) makes a deliberate `M502` + `M500` the right move after flashing, rather than an automatic wipe. The trims were taken as step 1 of a ladder that also had `DISABLE_M503` (~2700 B per upstream's comment) available; it was not needed, and `M503` kept working — which matters, because `M503` dumps are how EEPROM snapshots are archived.

Defaults were also neutralised so that a feature cannot act before it has been calibrated:

| Setting | Shipped value | Effect |
| --- | --- | --- |
| `ADVANCE_K` | `0.0` | Linear Advance is compiled in but does nothing until `M900 K` |
| `NONLINEAR_EXTRUSION` | `A=B=C=0` | Inert until `M592` |
| Skew factors | Identity | Inert until `M852` |
| `SHAPING_FREQ_X/Y/Z` | 40.0 Hz / 0.15 | Superseded by the measured `M593` values in EEPROM |
| `Z_AFTER_HOMING` | Off | No Z lift is applied after homing |
| `UBL_SAVE_ACTIVE_ON_M500` | Off | Disabled for AML compatibility, per the patch comment |
| `G29_RETRY_AND_RECOVER` | Off | Disabled for UBL |
| `ABL_BILINEAR_SUBDIVISION` | Off, as upstream already had it | A bilinear-mesh feature; unused under UBL |
| `CLASSIC_JERK` | Off | Junction deviation is the motion model instead; see below |

### The motion model is junction deviation, not classic jerk

`CLASSIC_JERK` is off, so the `DEFAULT_XJERK`/`DEFAULT_YJERK` values in the config are dead code and `M205` takes a `J` term instead of `X`/`Y` jerk. This matters because the two numbers are not comparable by size and the configurator's default is aggressive for a bed-slinger:

| Value | Source | Meaning |
| --- | --- | --- |
| `J0.1` | Configurator default, accepted by the recipe | Roughly equivalent to classic jerk 24 on this machine — far too aggressive |
| `J0.02` | Imposed during calibration, saved to EEPROM | The value the machine actually runs |

```gcode
M205 J0.02    ; junction deviation; this build has no classic jerk
M500          ; persist
```

## Rejected on purpose

| Option | Why it was refused |
| --- | --- |
| `FT_MOTION` | Marlin's fixed-timestep motion engine is not viable without an FPU, and the STM32F103 has none. Permanently out, and not a flash question |
| `-flto` (link-time optimisation) | Produces an image that does not boot on this board; tracked as upstream mriscoc issue #1083 |
| `S_CURVE_ACCELERATION` | Mutually exclusive with junction deviation in Marlin, and junction deviation won: the machine is calibrated around `M205 J0.02`, and enabling S-curve would change the motion profile every measurement was taken against |
| `SDCARD_READONLY` | Would break binary file transfer, which is the whole point of `BINARY_FILE_TRANSFER` |
| `MPC_AUTOTUNE_DEBUG` | ~870 B of flash for serial debug logging; there is no headroom for output that normal printing never needs |

## Traps in the upstream tree

Three things in and around the mriscoc tree cost real build or flash attempts, and none of them is a config error you can see from the option you were editing.

### Sanity checks couple options that look independent

Enabling `MULTIPLE_PROBING` above 0 with ProUI's extended menus aborts the build unless `EXTRA_PROBING` is exactly 1. `SanityCheck.h:1599` hard-errors with "PROUI_EX requires an EXTRA_PROBING value of 1", and the error surfaces from a file other than the one being edited, about a coupling the config gives no hint of.

```ini
#define MULTIPLE_PROBING 2
#define EXTRA_PROBING    1   ; required companion, not optional
```

### A UI symbol upstream never defines

`INPUT_SHAPING_Z` plus `SHAPING_MENU` makes `dwin.cpp` (lines 2863–2864) reference `ICON_ShapingZ` inside `drawInputShaping_menu()`, but `dwinui.h` only defines the X and Y aliases at lines 155–156. The build fails. This needs a source patch, shipped as [configs/patches/0002-proui-add-ICON_ShapingZ.patch](../configs/patches/0002-proui-add-ICON_ShapingZ.patch), mirroring the existing pattern:

```c
#define ICON_ShapingZ          CI(1,ICON_MoveZ)  // v2 fix: missing alias required by INPUT_SHAPING_Z shaping menu
```

Carry that line when pulling future upstream updates, and drop it once upstream defines the alias itself.

### The SD bootloader remembers the last filename

Creality's SD bootloader stores the name of the last file it flashed and silently skips any later attempt using that same name. Every early flash attempt used `firmware.bin` and produced no visible change — no error, no rename, just the old firmware booting. The procedure that works is a short unique filename each time, in the card root, with the flash verified by `M115` rather than by the screen. The used-name list is tracked in [firmware/flash-filenames.txt](../firmware/flash-filenames.txt) so a name is never repeated.

## Runtime behaviour worth knowing

- **`M503` dumps can watchdog-reset this build.** Dumping the full settings tree has triggered resets repeatedly; a reset mid-session has wiped freshly set `M593` values before a print started. Verify one setting with its own query instead (`M593`, `M306`, `M900`, `M851`). A reset does not corrupt EEPROM — mesh slots and saved values were intact after every observed reset.
- **`M20` lists only printable extensions.** An "empty" SD listing usually means no `.gcode`/`.gco` files, not a faulty slot. The slot round-trips writes, listings and deletes.
- **The filament runout sensor ships default-off.** `FIL_RUNOUT_ENABLED_DEFAULT false` is upstream's choice; the sensor is fitted here, so re-enable with `M412 S1` and `M500` after any EEPROM reset.
- **Mesh point count is partly a screen setting.** Mesh X/Y points also live in EEPROM (`meshSet`); a menu change does not survive a reboot without `M500`, and after `M502` the grid must be checked before re-probing — otherwise `G29` quietly produces a 5x5 mesh from a 7x7 build.
- **Input shaping Z is compiled but disabled.** `M593 Z F0` is deliberate; do not "restore" it without a measurement.

## What would be next if more flash existed

1128 bytes is not enough for another feature, so the next addition would have to buy its space by trimming something else. The candidates, with rough savings recorded during the research for this build:

| Candidate | Estimated saving | What is lost |
| --- | --- | --- |
| `PRINTCOUNTER` | ~0.9 K | Print statistics on the screen |
| Screen colour menu | ~1.2 K | UI colour selection |
| Temperature plot | ~0.8 K | On-screen plot graphs |
| `ESDiag` / lockscreen | ~0.8 K | Diagnostics screens and the screen lock |
| `PIDTEMPBED` to bang-bang bed control | ~2 K | PID holding on the bed heater |

These are estimates of the same order as the remaining headroom, so one trim buys roughly one feature — and only roughly. Any of them should be measured by an actual build before being promised; the figure that matters is the linker's, not the estimate's. RAM, with about 21 KB free, is not the limit.

[← Back to the project README](../README.md)
