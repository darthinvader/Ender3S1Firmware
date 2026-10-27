# Third-party components

This repository redistributes other people's work. This file records what, from where, under which terms, and what was deliberately left out.

## Shipped here

| Component | Path | Origin | Terms |
|---|---|---|---|
| Custom firmware images | `firmware/Ender3S1-F1-*.bin` | built from mriscoc/Professional Firmware in this repository | GPL-3.0 |
| Configuration and source changes | `configs/`, `scripts/`, `docs/` | this repository | GPL-3.0 |
| mriscoc reference builds | `firmware/upstream/*.bin` | [mriscoc/Ender3V2S1](https://github.com/mriscoc/Ender3V2S1) releases | GPL-3.0 |
| Creality stock firmware | `firmware/stock/stock-V1.0.6_C-F103-rollback.bin` | Creality official firmware package | proprietary, redistributed unmodified |
| Creality screen OS | `screen/official-v3.1.9-f401/firmware.zlib` | Creality official display package | proprietary, redistributed unmodified |
| mriscoc screen assets | `screen/mriscoc-dacai-assets/private/` | mriscoc/Ender3V2S1 `display assets` | GPL-3.0 |

## Deliberately not shipped

| Item | Why not |
|---|---|
| The mriscoc screen `firmware.zlib` (md5 `728a92a835df3f812271dc2be3482fe1`) | it is the file that bricked this screen. Only its hash is published, so it can be recognised and avoided. |
| `dcboot.bin` | it locks the display to Creality-only firmware. |
| The F401 mainboard image | wrong chip for this board; keeping it in the repository invites writing it to an F103 by mistake. |
| Creality's full display packages (`source-package.rar`, multi-megabyte asset sets) | redundant here - the recovered pairing is the two files above; the upstream packages remain available from Creality and mriscoc. |
| The upstream Marlin tree and the mriscoc configurator | they are large and versioned elsewhere. `scripts/bootstrap.sh` clones them at pinned commits instead of vendoring them. |

## Attribution

* **Marlin** - MarlinFirmware, GPL-3.0. Every configuration file in `configs/` is a derivative work.
* **Professional Firmware** - Miguel A. Risco-Castillo (MRiscoC). This project would not exist without it; the `M115` banner of the shipped build still credits him.
* **Creality** - the machine, the stock firmware and the display assets. The proprietary files here are unmodified vendor artifacts, included so that a broken machine can be restored without hunting through vendor CDNs.

## Removal policy

Vendor files are included for interoperability and repair, not as a redistribution of anyone's product. If a rights holder objects to any file in this repository, open an issue and it will be removed, and the documentation will point at the vendor source instead.

---

[<- Back to the project README](README.md)
