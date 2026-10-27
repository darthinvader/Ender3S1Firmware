# firmware/ - compiled images

Every image here is checksummed in [SHA256SUMS](SHA256SUMS). Verify before writing anything to a card:

```bash
sha256sum -c SHA256SUMS          # from inside firmware/
python3 ../scripts/check-vector-table.py *.bin
```

## Which one to flash

| Image | Size | md5 | What it is |
|---|---|---|---|
| [Ender3S1-F1-v2-20260730.bin](Ender3S1-F1-v2-20260730.bin) | 232,972 B | `6e11c30095187fd50a62fa75904379f0` | **current build.** UBL+IS+LA+MPC+BFT plus 7x7 mesh, smooth linear advance, MPC PTC, macros in EEPROM, skew correction, nonlinear extrusion, 32-block buffers. 99.5 % of the application region. |
| [Ender3S1-F1-UBL-IS-LA-MPC-BFT-20260728.bin](Ender3S1-F1-UBL-IS-LA-MPC-BFT-20260728.bin) | 226,408 B | `8eaf6819abf118859e6d2923e572e252` | previous build, kept as the known-good fallback for the current one |
| [upstream/Ender3S1-F1-UBL-IS-MPC-20240127.bin](upstream/Ender3S1-F1-UBL-IS-MPC-20240127.bin) | 217,344 B | `d9bc6984c99d9292873d39d37ab9deba` | mriscoc upstream, input shaping + MPC, no linear advance |
| [upstream/Ender3S1-F1-UBL-MPC-20260106.bin](upstream/Ender3S1-F1-UBL-MPC-20260106.bin) | 214,800 B | `1cf7006974f0e0b93745168da7626501` | mriscoc upstream, the first build flashed on this machine |
| [stock/stock-V1.0.6_C-F103-rollback.bin](stock/stock-V1.0.6_C-F103-rollback.bin) | 201,652 B | `fed5587ef885f3c123aec397d648bbcc` | **rollback.** official Creality V1.0.6_C, what the machine ran before any of this |

All five are for the STM32F103 board v2.4.S1.301. None of them is for an F401 board, and none is for an Ender 3 S1 **Pro**.

## The filename registry

[flash-filenames.txt](flash-filenames.txt) is not documentation - it is load-bearing. The SD bootloader silently refuses a filename it has already consumed, so every flash needs a new one and the used names have to be recorded somewhere. `scripts/flash-card.sh` reads this file, refuses to reuse a listed name, and appends what it used.

## A note on the vector tables

`scripts/check-vector-table.py` validates the first two words of each image. All five pass. One detail is worth recording because it looks alarming and is not:

| Image family | Initial stack pointer | Interpretation |
|---|---|---|
| mriscoc builds, including both shipped customs | `0x2000BFD8` | linked for 48 KiB SRAM, which is what this board has |
| Creality stock V1.0.6_C | `0x2000FFD8` | linked for 64 KiB SRAM - how Creality built it |

The stock image is redistributed unmodified, so the checker reports that difference as a note rather than a failure.

## What was left out on purpose

The F401 image (`Ender3S1-F4-*.bin`) that shipped alongside the F103 downloads is not here. It is the wrong chip for this board, and a repository that contains it is a repository where someone eventually flashes it. See [../THIRD-PARTY.md](../THIRD-PARTY.md).

---

[<- Back to the project README](../README.md)
