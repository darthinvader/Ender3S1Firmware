# configs/ - the exact build input

These are the files that were compiled, not a description of them. `scripts/bootstrap.sh` copies a variant folder into the pinned upstream Marlin tree and applies the source patch; nothing is edited by hand afterwards.

## Variants

| Folder | Produces | Notes |
|---|---|---|
| [Ender3S1-F1-v2/](Ender3S1-F1-v2) | `Ender3S1-F1-v2-20260730.bin` | the current build, 232,344 / 233,472 B |
| [Ender3S1-F1-UBL-IS-LA-MPC-BFT/](Ender3S1-F1-UBL-IS-LA-MPC-BFT) | `...-20260728.bin` | the previous build, kept as the fallback |

Each folder holds `Configuration.h`, `Configuration_adv.h`, `Version.h`, `platformio.ini` and the configurator's own `log.txt`. The two variants differ only in the machine name and the v2 feature set.

## recipes/

[recipes/](recipes) holds the configurator invocation and a line-by-line account of every hand edit, with `file:line` references into the variant folders: what was changed, why, and what it cost in flash. If you read only one file in this directory, read the v2 recipe.

## features/

[features/BFT.json](features/BFT.json) is a custom configurator feature file. It re-enables `BINARY_FILE_TRANSFER` and `CUSTOM_FIRMWARE_UPLOAD` after the board file disables them to save flash - which is what makes cable flashing possible at all.

## patches/

| Patch | Kind | Role |
|---|---|---|
| [0001-machine-configs.patch](patches/0001-machine-configs.patch) | record | the full configuration delta from the upstream default to this machine. Kept for review; **not** applied during bootstrap, because the variant folders already contain the result. |
| [0002-proui-add-ICON_ShapingZ.patch](patches/0002-proui-add-ICON_ShapingZ.patch) | required | the one-line source fix without which the build fails when `INPUT_SHAPING_Z` and `SHAPING_MENU` are enabled |

`0002` is applied by bootstrap against the pristine upstream tree. When pulling a newer mriscoc release, check whether upstream has added the alias; if it has, the patch will refuse to apply and can be dropped.

---

[<- Back to the project README](../README.md)
