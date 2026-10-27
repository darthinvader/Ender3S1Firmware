# The DACAI screen: assets, reflashing and how it was bricked

The 4.3-inch screen is not a display panel hanging off the mainboard — it is a separate computer with its own operating system and its own asset partition, flashed from its own microSD slot. That is why it can be dead while the printer is healthy, and why fixing it means flashing the right pair of files rather than the mainboard. This page records what bricked it in July 2026, what revived it on 2026-07-29, and the rules that follow.

## What the screen is

| Property | Value |
|---|---|
| Module | DACAI, 4.3 inch color |
| Controller | Allwinner F1C100s |
| PCB label | `3102020079` |
| Firmware layer | screen OS, `firmware.zlib` |
| Asset layer | `private/` (images, icons, fonts, `config.txt`) |
| Flash medium | the screen's **own** microSD slot (screen removed from the front panel) |

The asset folder's [config.txt](../screen/mriscoc-dacai-assets/private/config.txt) is five lines and carries the module's serial/power parameters:

```ini
R1=07; 115200
R2=0C;
R3=6F;
RFA=01;
RFC=18;
```

## The July 2026 failure

The first symptom was partial: the screen showed the boot logo and live temperature/position values, but **no menu**, and turning or clicking the knob opened nothing. The mainboard was healthy the whole time — it answered over serial and reported normal temperatures.

Attempts to repair it by reflashing the screen made it worse. The flash that did the damage was mriscoc's own screen `firmware.zlib`, which took the screen from "no menu" to **black but backlit**: powered, backlight on, nothing drawn.

| Item | Value |
|---|---|
| File | mriscoc screen `firmware.zlib` |
| MD5 | `728a92a835df3f812271dc2be3482fe1` |
| Effect on this machine | black screen, backlight on |
| Shipped in this repo | **no, deliberately** |

It is not shipped here, and it should not be. The hash is documented so the file can be recognized and refused.

## Never flash these two files

| File | What it does | Recognize it by |
|---|---|---|
| mriscoc screen `firmware.zlib` | blacks the screen (backlight stays on); happened here in July 2026 | md5 `728a92a835df3f812271dc2be3482fe1` |
| `dcboot.bin` | locks the screen to Creality-only firmware (mriscoc/Ender3V2S1 issue #966) | filename |

Check any `firmware.zlib` you are about to copy to a card:

```bash
# the file you are about to copy to the card
md5sum firmware.zlib
```

If the hash is `728a92a835df3f812271dc2be3482fe1`, stop. The good file is `b99abe7a1388e52e2439b8b85c64fbc6`.

## What revived it (2026-07-29)

The screen came back with a **pair** of files on one card: an official Creality screen OS image plus the mriscoc asset set.

| Layer | File in this repo | MD5 | Size |
|---|---|---|---|
| Screen OS | [screen/official-v3.1.9-f401/firmware.zlib](../screen/official-v3.1.9-f401/firmware.zlib) — official Creality V3.1.9 (Two_C) F401 | `b99abe7a1388e52e2439b8b85c64fbc6` | 394,835 B |
| Assets | [screen/mriscoc-dacai-assets/private/](../screen/mriscoc-dacai-assets/private/config.txt) — mriscoc DACAI set | — | 7 files, 314,782 B |

The OS image is an F401-era Creality build and runs fine on this F103-era DACAI module; the pairing that matters is the one in the next section, not the OS image's nominal board generation.

The asset set, file by file:

| File | Size |
|---|---|
| `config.txt` | 47 B |
| `icon/2.zico` | 95,535 B |
| `icon/9.zico` | 131,197 B |
| `image/0.jpg` | 11,065 B |
| `image/1.jpg` | 49,076 B |
| `truefont/font.ttf` | 27,836 B |
| `truefont/truefont.ini` | 26 B |
| **Total** | **314,782 B** (~324 KiB allocated on disk) |

## The pairing rule

The screen assets must match the **mainboard** firmware family, not the screen OS version:

| Mainboard firmware | Screen assets required |
|---|---|
| Stock Creality (V1.0.6_C and similar) | official Creality DACAI assets |
| mriscoc or any custom Marlin build | mriscoc DACAI assets ([screen/mriscoc-dacai-assets/private/](../screen/mriscoc-dacai-assets/private/config.txt)) |

Mixing the two produces a blank or black screen even though both flashes reported success. A flash that "finished" is not evidence that the pairing is right.

## The asset partition limit is real

The screen rejects an asset set that is too large. This was measured on this machine:

| Asset set size | Result |
|---|---|
| 3.3 MB, multi-language | **rejected** — error mentions `max 1mb` |
| 1.1 MB, English only | accepted |
| 314,782 B (mriscoc set here) | accepted |

So the usable ceiling sits between roughly 1.1 MB and 3.3 MB; the exact boundary is **not recorded**. Anything in the hundreds of kilobytes, like the set shipped here, is safely inside it. Large multi-language packs are not.

## Flashing the screen

Card preparation is the number one failure point, so do it deliberately:

- **MBR** partition table, **FAT32**, **4096-byte allocation unit**
- **8 GB or smaller** is safest
- the screen's slot takes a **microSD** card (the mainboard slot is a full-size SD — do not confuse the two)

```bash
# rebuild the partition table and filesystem; check the device name first
sudo parted -s /dev/sdX mklabel msdos mkpart primary fat32 1MiB 100%
sudo mkfs.vfat -F 32 -s 8 /dev/sdX1
```

`-s 8` is 8 sectors per cluster, i.e. 4096-byte allocation units. `/dev/sdX` stands for the card — confirm with `lsblk` before running anything destructive.

Procedure:

1. Copy both the `private/` folder and `firmware.zlib` to the **root** of the card.
2. Power the printer **off**.
3. Insert the card into the **screen's own microSD slot** — the screen has to come off the front panel; this is not the mainboard slot.
4. Power **on**. The screen turns blue/orange for about a minute while it flashes.
5. When it changes color, power **off**, remove the card, reassemble.
6. Power **on** and let it boot.

### First boot after a screen flash

The Creality logo holds for around **30 s** on the first boot after a screen flash before the UI comes up. That is normal. Do not power-cycle during it, and do not conclude the flash failed.

## DACAI or DWIN

The two screen families take different asset folders, and the only reliable way to tell them apart is the label on the screen's PCB:

| Family | Asset folder | This machine |
|---|---|---|
| **DACAI** | `private/` | **yes** — PCB `3102020079` |
| **DWIN** | `DWIN_SET/` | no |

Flashing the wrong family does not brick anything permanently, but the screen stays blank until the matching set is flashed. Check the label before blaming the card.

## Recovery ladder: the screen stays blank

Work down this list in order — the first item is the most common cause by a wide margin.

1. **Re-check the card format.** MBR + FAT32 + 4096-byte allocation units. This is the number one failure point; a card that mounts fine on the PC can still be rejected by the screen.
2. **Try a smaller card.** 8 GB or smaller is the safe range.
3. **Verify where `private` landed.** It must be `private` at the card root, not nested one level deeper (e.g. `private/private` or `assets/private`). The same applies to `firmware.zlib` — root of the card.
4. **Verify the pairing.** mriscoc mainboard firmware needs mriscoc assets; stock mainboard firmware needs official Creality assets. A mismatched pair gives a blank screen on a technically successful flash.
5. **Reflash the pair together.** Both `firmware.zlib` and `private/` on the same card, screen OS included, rather than assets alone.

[← Back to the project README](../README.md)
