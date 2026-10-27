# calibration/ - what the machine was actually set to

Two EEPROM dumps, kept as evidence rather than as recommendations. Both are raw `M503` output plus, in the newer one, the bed mesh grid.

| File | Taken | What it captures |
|---|---|---|
| [eeprom-Ender3S1-F1-v2-20260730.txt](eeprom-Ender3S1-F1-v2-20260730.txt) | 2026-07-30 | the current build's settings plus the 7x7 mesh, probed hot at 60 C |
| [eeprom-20260729-uber-build.txt](eeprom-20260729-uber-build.txt) | 2026-07-29 | the previous build's settings and the complete `M306` MPC line |

## These dumps are snapshots, not the final values

One value changed after the last dump was taken, and it is the one most often copied by mistake:

| Setting | In the 2026-07-30 dump | Final |
|---|---|---|
| Input shaping | `M593 X F55 D0.15`, `M593 Y F58 D0.15` | `M593 X F48 D0.08`, `M593 Y F48 D0.08` |

The dump was taken before the last frequency sweep. For the authoritative list, with the measurement method behind each value, use [../docs/CALIBRATION.md](../docs/CALIBRATION.md).

## Why they are here at all

Because a settings dump is the only way to answer the question "what exactly was this machine running" months later, and because a calibration restore needs a starting point that is known to have been measured rather than remembered.

Treat every number as belonging to this one printer. Bed bow, probe offsets, Z offset and shaping frequencies are machine properties, not firmware properties.

---

[<- Back to the project README](../README.md)
