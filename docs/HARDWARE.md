# The machine: hardware and memory layout

An Ender 3 S1 (non-Pro): Sprite direct-drive extruder, CR Touch probe, Creality v2.4.S1.301 mainboard on an STM32F103RCT6, 4.3-inch DACAI screen. The numbers on this page are what decide which firmware is buildable for it. The MCU has 256 KiB of flash and 48 KiB of RAM, and the shipped v2 build already occupies 99.5 % of the flash — so feature work on this machine is subtraction as much as addition.

## Machine specification

| Property | Value | Where it lives |
|---|---|---|
| Model | Creality Ender 3 S1, **non-Pro** | — |
| Build volume | 220 x 220 x 270 mm | `X_BED_SIZE`, `Y_BED_SIZE`, `Z_MAX_POS` in [Configuration.h](../configs/Ender3S1-F1-v2/Configuration.h) |
| Extruder | Sprite direct drive, single | `EXTRUDERS 1` |
| Hotend thermistor | `TEMP_SENSOR_0 1` (T1, stock) | `Configuration.h` |
| Bed probe | CR Touch, wired to the BLTouch header | `#define BLTOUCH` |
| Probe offsets | X -31.80, Y -40.50 mm from the nozzle | `NOZZLE_TO_PROBE_OFFSET`; live value `M851` |
| Mainboard | Creality v2.4.S1.301 | `MOTHERBOARD BOARD_CREALITY_V24S1_301` |
| MCU | STM32F103RCT6, 256 KiB flash / 48 KiB RAM | chip marking, read 2026-07-30 |
| Screen | DACAI 4.3", Allwinner F1C100s, PCB 3102020079 | see [SCREEN.md](SCREEN.md) |
| Host serial | 250000 baud, port 1 | `SERIAL_PORT 1`, `BAUDRATE 250000` |
| Filament runout | PC15, switch type, trigger state HIGH, 200 mm | `FILAMENT_RUNOUT_SENSOR` |
| Steps/mm | X80 Y80 Z400, E428 | `M92` in EEPROM; compiled default `E424.9` |

## The MCU, and why the marking mattered

The chip marking was read directly on 2026-07-30: **STM32F103RCT6, 256 KiB flash and 48 KiB RAM, no more**. The build environment agrees — the PlatformIO environment `STM32F103RC_creality` reports `STM32F103RCT6 72MHz, 48KB RAM, 256KB Flash` ([logs/build-Ender3S1-F1-v2.log](../logs/build-Ender3S1-F1-v2.log)).

That reading closed a question that had been open for weeks: the part really is 256 KiB / 48 KiB, so the flash ceiling for this board is final. The STM32F103 is a Cortex-M3 part with no FPU, which permanently rules out floating-point-heavy motion features such as `FT_MOTION`; the shipped configuration keeps it disabled (`//#define FT_MOTION` in [Configuration_adv.h](../configs/Ender3S1-F1-v2/Configuration_adv.h)) and it stays that way.

## Memory map

| Region | Address range | Size | Contents |
|---|---|---|---|
| Bootloader | `0x08000000` - `0x08007000` | 28 KiB (28,672 B) | Creality serial/SD bootloader — not written by a firmware flash |
| Application | `0x08007000` - `0x08040000` | 233,472 B (228 KiB) | Marlin + mriscoc, this is the linker's hard limit |
| Flash (total) | `0x08000000` - `0x08040000` | 256 KiB | — |
| RAM | `0x20000000` - `0x2000C000` | 48 KiB | statics, planner, stack, heap |

The application region is simply "flash minus bootloader": 256 KiB - 28 KiB = 228 KiB = 233,472 B, and that is the exact number the linker enforces:

```text
Flash: [==========]  99.5% (used 232344 bytes from 233472 bytes)
RAM:   [======    ]  57.1% (used 28064 bytes from 49152 bytes)
```

The 28 KiB figure is not an estimate: it is the offset the S1's F103 bootloader occupies, and any application for this board must start at `0x08007000` or higher (see [identifying your board](#identifying-your-board) for the check).

## The flash budget, and what it implies

| Resource | Used by the v2 build | Budget | Utilization | Left |
|---|---|---|---|---|
| Flash | 232,344 B | 233,472 B | 99.5 % | **1,128 B** |
| RAM | 28,064 B | 49,152 B | 57.1 % | 21,088 B (~ 20.6 KiB) |

- **Flash is the binding constraint, RAM is not.** There is roughly 20 KiB of RAM free, and the v2 build deliberately spends some of it: serial RX buffer 512 B, TX buffer 64 B, command buffer 96 B, planner block buffer 32 — all SRAM costs, none of them flash costs.
- **The 1,128 B of headroom was bought, not found.** The v2 build disables `EEPROM_CHITCHAT` (Marlin's feedback chatter on EEPROM commands) and `EEPROM_INIT_NOW` to make room for its feature set; neither has functional impact. Both are commented out in [Configuration.h](../configs/Ender3S1-F1-v2/Configuration.h).
- **Every further feature needs a trim elsewhere.** At 99.5 % there is no room for a new subsystem without removing comparable code in the same build. Treat any new `#define` as a trade.
- **The budget is per build, not per machine.** A smaller feature set leaves proportionally more room; the v2 recipe and its notes are in [configs/recipes/Ender3S1-F1-v2.ini](../configs/recipes/Ender3S1-F1-v2.ini).

## SD bootloader behavior

Three properties of this bootloader cause almost every flash mystery on this board:

| Property | Consequence |
|---|---|
| It records the last filename it flashed and silently skips any later flash that reuses that name | Every attempt needs a fresh unique filename; never `firmware.bin`. The used-name ledger is [firmware/flash-filenames.txt](../firmware/flash-filenames.txt) |
| It gives no visual feedback | The screen stays dead through a mainboard flash. A dark screen is not a failure signal |
| Firmware defaults to 250000 baud (mriscoc), stock Creality used 115200 | A host that reconnects at 115200 sees no answer and looks like a failed flash when the flash actually worked |

Verify the running image over serial instead of trusting the display:

```gcode
M115        ; firmware name, version, capabilities
```

## Thermistor and probe

`TEMP_SENSOR_0 1` is the stock T1 thermistor of the non-Pro Sprite. Builds configured for **T13** target the Sprite **PRO** sensor and are not correct for this machine — check the sensor define before flashing anything built for "Sprite".

The CR Touch is wired to the BLTouch connector, so the firmware enables the BLTouch driver rather than a Creality-specific probe mode. Offsets are `NOZZLE_TO_PROBE_OFFSET { -31.8, -40.5, 0 }` in the configuration and `M851 X-31.80 Y-40.50 Z-3.10` in EEPROM ([calibration/eeprom-Ender3S1-F1-v2-20260730.txt](../calibration/eeprom-Ender3S1-F1-v2-20260730.txt)).

The practical consequence: the probe axis is 31.8 mm in X and 40.5 mm in Y away from the nozzle, so probe-reachable points and paper-test corners are roughly 45 mm apart near the bed edges and legitimately disagree there. Mesh corner values and a paper test at the nozzle corners are two different measurements.

## Filament runout sensor

The sensor is fitted on this machine and connected to **PC15**; it is a switch type whose trigger state is HIGH.

| Setting | Value |
|---|---|
| Macro | `FILAMENT_RUNOUT_SENSOR` |
| Pin | PC15 |
| Type | switch (`FIL_RUNOUT_STATE HIGH`, internal pulldown) |
| Detection distance | 200 mm |
| Action | `M600` (ADVANCED_PAUSE) |
| Startup default | **disabled** (`FIL_RUNOUT_ENABLED_DEFAULT false`) |

mriscoc compiles the runout support but ships it disabled, so a freshly flashed or EEPROM-reset machine ignores the sensor until it is enabled and saved:

```gcode
M412 S1     ; enable runout detection
M500        ; persist it
```

The stored state reads back as `M412 S1 D200.00 ; Sensor ON` in the EEPROM dump.

## Board variants: F103 vs F401

Two mainboard MCUs exist in the wild for this printer family, and their firmware images are **not** interchangeable:

| MCU | mriscoc binary family | Application placement | Status here |
|---|---|---|---|
| STM32F103RCT6 | F1 / F103 builds | above the 28 KiB bootloader, `0x08007000` | this machine |
| STM32F401 | F4 / F401 builds | different vector-table offset (64 KiB) | never boots here |

The vector table offset differs between the families, so an image built for the other MCU is not a valid image for this board — it is not a "maybe it works" situation. Flash only what matches the chip.

## Identifying your board

Do this before flashing anything; each step takes a minute and prevents the expensive mistakes.

1. **Read the chip marking** on the mainboard: `STM32F103RCT6` means F103 and F1 binaries. An F401 marking means the opposite.
2. **Read the mainboard silkscreen**: this board is `v2.4.S1.301`, which corresponds to `BOARD_CREALITY_V24S1_301` in the configuration.
3. **Read the screen's PCB label** (screen removed from the front panel): **DACAI** vs **DWIN** decides which asset folder is valid. This machine is DACAI, PCB `3102020079`. Details in [SCREEN.md](SCREEN.md).
4. **Sanity-check a candidate binary's vectors** before trusting a filename — the first two words of the image must look sane for this family:

```bash
# from the repository root
xxd -l 16 firmware/Ender3S1-F1-v2-20260730.bin
```

```text
00000000: d8bf 0020 c592 0008 0d93 0008 0d93 0008
```

The first word is the initial stack pointer (`0x2000BFD8`, inside the 48 KiB of RAM); the second is the reset handler (`0x080092C5`, inside the application region above `0x08007000`). An F4 image shows a different picture.

5. **Confirm what is actually running** with `M115` after boot rather than what you believe you flashed.

[← Back to the project README](../README.md)
