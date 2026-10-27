# Flashing: mainboard and screen

The Ender 3 S1 has two independently flashable processors: the STM32F103 mainboard and the DACAI display's own controller. They are flashed from different SD slots with different card layouts, and they must be flashed in the right order to stay recoverable. This is the procedure for both.

Every binary in this repository is checksummed. Before you write anything to a card:

```bash
./scripts/verify-artifacts.sh
```

That verifies the checksums, checks that each `.bin` has a plausible Cortex-M vector table, and confirms the shipped configuration still matches what this documentation claims.

## What you need

| Item | Detail |
|---|---|
| Mainboard card | full-size SD (the front slot of the printer is full-size SD, not microSD); microSD works in an adapter |
| Screen card | microSD, 8 GB or smaller is safest, separate card from the mainboard one |
| Card reader | one that lets you set the partition table and cluster size, or `parted` + `mkfs.vfat` on Linux |
| Host | anything that can talk to the printer over USB serial, or OctoPrint |
| Rollback | [stock/stock-V1.0.6_C-F103-rollback.bin](../firmware/stock/stock-V1.0.6_C-F103-rollback.bin) on the same card, ready |

## 1. Mainboard over SD (the path that always works)

This is the primary flash path. It was used for every firmware in this repository and it has never needed the case opened.

### Card layout

| Property | Value |
|---|---|
| Partition table | MBR (msdos) |
| Filesystem | FAT32 |
| Cluster size | 4096 bytes (`mkfs.vfat -F 32 -s 8`) |
| Card size | 16 GB or smaller |
| Contents of root | exactly one `.bin`, no folders, no other files |
| Filename | 8.3 uppercase name that has **never** been used on this printer before |

`scripts/flash-card.sh` builds exactly this layout and refuses to reuse a filename:

```bash
# show the plan, change nothing
./scripts/flash-card.sh --device /dev/sdX --bin firmware/Ender3S1-F1-v2-20260730.bin

# execute (asks you to type the device path first)
./scripts/flash-card.sh --device /dev/sdX --bin firmware/Ender3S1-F1-v2-20260730.bin --yes
```

Doing it by hand is fine too:

```bash
sudo wipefs -a /dev/sdX
sudo parted -s /dev/sdX mklabel msdos
sudo parted -s /dev/sdX mkpart primary fat32 1MiB 100%
sudo mkfs.vfat -F 32 -s 8 -n FWFLASH /dev/sdX1
sudo mount /dev/sdX1 /mnt
sudo cp firmware/Ender3S1-F1-v2-20260730.bin /mnt/F1ABCDEF.bin
sync
md5sum /mnt/F1ABCDEF.bin firmware/Ender3S1-F1-v2-20260730.bin
sudo umount /mnt
```

### Procedure

1. Power the printer off and wait about 15 seconds.
2. Unplug the USB cable. The flash path is not reliable with a host attached.
3. Insert the card into the front slot of the printer (the mainboard slot).
4. Power on. Wait up to 60 seconds.
5. **The screen shows nothing during a mainboard flash.** A black screen here is expected and is not a failure signal - the stock screen firmware is not running yet at that point.
6. Power off, remove the card.
7. Reconnect USB, power on.

### Confirming it worked

Two independent signals, either is sufficient:

```gcode
M115
; must report: FIRMWARE_NAME: ... 2.1.4 MRiscoC ... Ender3S1-F1-v2
```

* Connect at **250000 baud**, not 115200. This build runs at 250000 (mriscoc default); stock Creality firmware ran at 115200. Silence at 115200 is the single most common false alarm - it does not mean the flash failed.
* Check the card on your PC afterwards. The bootloader renames or removes the file it consumed.

### The filename rule

The Creality SD bootloader remembers the last filename it flashed and silently skips any later attempt that reuses that name. This is why five attempts with `firmware.bin` produced nothing, and it is why every flash in this repository carries a unique 8-character name.

| | |
|---|---|
| Never use | `firmware.bin` |
| Always use | a name that is not in [flash-filenames.txt](../firmware/flash-filenames.txt) |
| Record | append the name you used to that file |

`scripts/flash-card.sh --next-name` prints an unused name and the script appends what it used automatically.

### If nothing happened

Work down this ladder and stop at the first step that works. Steps 1-2 are cheap; 3-4 need the case open.

| Step | Action | Notes |
|---|---|---|
| 1 | Try another fresh unique filename | same card, same image |
| 2 | Try a different card, reformatted | card format is the number one failure cause |
| 3 | BOOT0 pad to 3.3 V at power-on, then `stm32flash -w <image>.bin /dev/ttyUSB0` | the STM32 ROM bootloader then speaks on the existing USB-serial adapter; this is the documented recovery path, not something this repository exercised |
| 4 | ST-Link on the SWD pads | needs the case open and a probe |

Step 3 restores full control even if the application image is invalid, because the ROM bootloader is in mask ROM and cannot be erased. There is no realistic way to permanently brick this board by writing a bad application image.

## 2. Mainboard over USB (binary file transfer)

The custom build is compiled with `BINARY_FILE_TRANSFER` and `CUSTOM_FIRMWARE_UPLOAD`, which is exactly what the OctoPrint `Firmware Updater` plugin's `marlinbft` profile needs. Confirm the capability first:

```gcode
M115
; look for: Cap:CUSTOM_FIRMWARE_UPLOAD:1
```

Three things to know before using it:

* **Precompiled mriscoc builds cannot be flashed this way.** Every official mriscoc release ships `BINARY_FILE_TRANSFER:0`. The capability exists here only because this repository's configuration re-enables it.
* **Never push a `.bin` over plain ASCII upload (`M28` without `B1`).** Binary data that happens to contain the byte sequence `M29` terminates the transfer mid-file; the IS build contains one at offset 204858. The result is a truncated image plus a resend storm.
* **This path is implemented but has not been battle-tested on this machine.** The SD path is the one with a track record here. Treat cable flashing as the convenient option and SD as the reliable one.

## 3. Screen

The screen is a separate computer with separate firmware and its own microSD slot, reachable only with the front panel off. It also has a pairing constraint: the asset set must match the mainboard firmware family.

| Mainboard firmware | Screen assets to use |
|---|---|
| stock Creality (including the rollback image) | official Creality DACAI assets |
| this custom build, or any mriscoc build | [screen/mriscoc-dacai-assets/private/](../screen/mriscoc-dacai-assets/private) |

Full procedure, the asset-size ceiling, the `dcboot.bin` trap and the file that bricked this screen in the first place: [docs/SCREEN.md](SCREEN.md).

## 4. Rolling back

Rolling back is the same SD procedure with the stock image, followed by the matching screen assets:

```bash
# 1. verify the rollback image is intact
( cd firmware && sha256sum -c SHA256SUMS )

# 2. write it with a fresh unique name
./scripts/flash-card.sh --device /dev/sdX --bin firmware/stock/stock-V1.0.6_C-F103-rollback.bin
```

Then: write the official screen assets, and expect the machine to be uncalibrated. The stock image does not understand this repository's EEPROM layout, so treat every setting in [docs/CALIBRATION.md](CALIBRATION.md) as gone and restore what the stock firmware supports.

| | Rollback to stock | Roll forward again |
|---|---|---|
| Mainboard image | `firmware/stock/stock-V1.0.6_C-F103-rollback.bin` | `firmware/Ender3S1-F1-v2-20260730.bin` |
| Screen assets | official Creality DACAI set | `screen/mriscoc-dacai-assets/private/` |
| Serial baud | 115200 | 250000 |
| Calibration | re-enter by hand | restore from [docs/CALIBRATION.md](CALIBRATION.md) |

## 5. After any flash: the checklist

Run this in order. It is the difference between "the flash worked" and "the printer prints".

- [ ] `M115` reports the expected firmware name and build date, at 250000 baud.
- [ ] `M503` is **not** used to check settings - it can trigger a watchdog reset on this build. Query one setting at a time (`M92`, `M851`, `M593`, `M900`, `M412`).
- [ ] EEPROM state is what you expect. `M502` + `M500` resets to compiled defaults; skipping both keeps the previous calibration. The custom build deliberately has `EEPROM_INIT_NOW` disabled so a reflash does **not** wipe your settings.
- [ ] Nozzle and probe offsets: `M851` must report `X-31.80 Y-40.50`.
- [ ] Input shaping: `M593` must report `X F48.00 D0.08` and `Y F48.00 D0.08`.
- [ ] Linear advance: `M900` must report `K0.08 U0.02`.
- [ ] Filament runout: `M412` must report the sensor ON. It ships disabled by default and must be re-enabled with `M412 S1` + `M500` after any EEPROM reset.
- [ ] Mesh: `G29 T` shows a 7x7 grid, and `M420 V` reports a valid mesh with bed leveling ON.
- [ ] `G28`, then a first-layer test print. Judge the first layer by eye, not by a paper test.

If any value is wrong, [docs/CALIBRATION.md](CALIBRATION.md) has the full restore sequence with the G-code in order.

## Hard rules

These exist because each one cost a failed print or a wasted evening:

1. Never reuse an SD flash filename.
2. Never flash the screen with the mriscoc `firmware.zlib`, and never flash `dcboot.bin`.
3. Never run `M503` or `C29` on this build unless you accept a watchdog reset.
4. Do not send commands to the printer while it is printing. Read-only monitoring only.
5. Verify the image you are about to flash. `./scripts/verify-artifacts.sh` is one command.

---

[<- Back to the project README](../README.md)
