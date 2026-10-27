# screen/ - DACAI display OS and assets

The display is a separate computer with its own microSD slot, its own firmware and its own asset partition. It is flashed from the front panel, not from the mainboard slot, and its assets must match the mainboard firmware family.

## The pairing rule

| Mainboard firmware | Screen content |
|---|---|
| stock Creality, including the rollback image | official Creality DACAI assets |
| this custom build, or any mriscoc build | [mriscoc-dacai-assets/private/](mriscoc-dacai-assets/private) |

Mixing the two families produces a blank or black screen even though both flashes report success.

## What is here

| Path | What it is |
|---|---|
| [official-v3.1.9-f401/firmware.zlib](official-v3.1.9-f401/firmware.zlib) | official Creality V3.1.9 (Two_C) F401 screen OS, 394,835 B, md5 `b99abe7a1388e52e2439b8b85c64fbc6` |
| [mriscoc-dacai-assets/private/](mriscoc-dacai-assets/private) | the matching asset set: `config.txt`, `icon/2.zico`, `icon/9.zico`, `image/0.jpg`, `image/1.jpg`, `truefont/font.ttf`, `truefont/truefont.ini` |

Both belong on the **same** card, at its root, as `firmware.zlib` plus the `private` folder.

## What is not here, on purpose

| File | Why not |
|---|---|
| mriscoc's `firmware.zlib`, md5 `728a92a835df3f812271dc2be3482fe1` | this is the file that turned the screen black-but-backlit. Only its hash is published, so the file can be recognised and never used. |
| `dcboot.bin` | locks the display to Creality-only firmware. |

## Procedure

Card: MBR partition table, FAT32, 4096-byte allocation units, 8 GB or smaller is safest. Copy `firmware.zlib` and the `private` folder to the card **root**.

```text
power off  ->  card into the SCREEN slot (front panel off)  ->  power on
           ->  screen flashes blue/orange for about a minute  ->  power off
           ->  card out, panel back on, power on
```

The first boot after a screen flash holds the Creality logo for around 30 seconds. That is normal; do not power cycle during it.

Full description, the asset-size ceiling, the DACAI-vs-DWIN check and the recovery ladder: [../docs/SCREEN.md](../docs/SCREEN.md).

## Checksums

```bash
sha256sum -c SHA256SUMS          # from inside screen/
```

---

[<- Back to the project README](../README.md)
