# logs/ - build logs as produced

| File | Build | Result |
|---|---|---|
| [build-Ender3S1-F1-v2.log](build-Ender3S1-F1-v2.log) | `Ender3S1-F1-v2`, 2026-07-30 | SUCCESS in 43.57 s, 232,344 / 233,472 B flash, 28,064 / 49,152 B RAM, no warnings |
| [build-Ender3S1-F1-UBL-IS-LA-MPC-BFT.log](build-Ender3S1-F1-UBL-IS-LA-MPC-BFT.log) | the previous build, 2026-07-28 | the full first-build log, including the failed attempts that led to the configuration changes |

These are committed because the memory report at the end of a build is the primary evidence for the flash-budget claims in the documentation. `./scripts/build.sh` writes new logs into `build/logs/`, so a rebuild never overwrites the record.

---

[<- Back to the project README](../README.md)
