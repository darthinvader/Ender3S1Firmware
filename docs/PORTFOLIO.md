# This project on a CV

Short, honest, and checkable. Every number here comes from a file in this
repository, and each row links to where it is proven.

![Architecture](img/architecture.svg)

## One line

> Custom Marlin firmware for a Creality Ender 3 S1 that fits a 1,128-byte
> flash budget, with a measured feature-cost harness and a local configurator
> that compiles, checks and writes the image.

## Thirty seconds

I run a Ender 3 S1 on mriscoc's Professional Firmware (Marlin 2.1.x) on an
STM32F103 with 233,472 bytes of usable flash. I specify the configuration, keep
the build reproducible against pinned upstream commits, and measured what every
single option costs by compiling it on and off - 66 of the 71 catalogue features
have a real byte cost, not an estimate. On top of that I built a local
configurator that predicts the image size to the byte, refuses combinations that
cannot fit, compiles any mriscoc release or a git branch, and writes the SD card
for both the mainboard and the display panel. The display bricked during the
work; I diagnosed it, recovered it, and the recovery kit is in the repository.

## CV bullets (paste-ready)

- Rebuilt a Creality Ender 3 S1 on Marlin 2.1.x / mriscoc ProUI within a
  **1,128-byte flash margin** (232,344 of 233,472 bytes), choosing features by
  measured cost rather than guesswork.
- Built a **feature-cost measurement harness** (`tools/configurator/measure.py`)
  that compiles every option on and off and writes the delta back into a
  catalogue: 71 features, 66 measured, plus a predictor whose error on the
  shipped build is **0 bytes**.
- Wrote a **local configurator** (Python stdlib HTTP service + vanilla JS, no
  framework, no build step) that compiles the selected firmware, verifies the ARM
  vector table, and writes a bootable SD card for the mainboard and the display,
  md5-checking every copy.
- Recovered a **bricked display panel** by isolating a mismatched asset pack,
  and shipped the recovery kit plus the evidence trail
  ([docs/SCREEN.md](SCREEN.md)).
- Kept the whole chain reproducible and enforced: pinned upstream commits,
  committed binaries with manifests, `make verify` (checksums, vector tables,
  configuration assertions, documentation links, 14 live service checks) and
  three GitHub Actions workflows.

## What is mine, and what is upstream

Recruiters ask. This is the honest split.

| Mine | Upstream (mriscoc / Marlin / Creality) |
|---|---|
| The configuration as a versioned artefact, its rationale, and every hand edit with `file:line` | Marlin itself and mriscoc's ProUI layer |
| The measurement harness, the feature catalogue and the size predictor | The compiler and PlatformIO |
| The configurator (service, UI, build pipeline, SD-card writer, bundle) | The firmware it compiles |
| The screen recovery procedure and the verified OS/asset pairing | Creality's display OS images |
| The documentation, the verification gates and CI | The bootloader on the board |

I do not claim to have written the firmware. I claim to have specified,
measured, built, recovered, documented and automated it - which is what the job
actually is.

## Skills, each with a receipt

| Skill | Evidence |
|---|---|
| Embedded C configuration and constraint budgeting | [docs/DESIGN-NOTES.md](DESIGN-NOTES.md) - every choice, its cost in bytes, and what was rejected |
| Build systems and reproducibility | [docs/BUILD.md](BUILD.md), pinned commits in [configs/](../configs) |
| Measurement instead of estimation | [tools/configurator/README.md](../tools/configurator/README.md) - the catalogue and the prediction error |
| Python service and tooling | [tools/configurator/server.py](../tools/configurator/server.py), [scripts/](../scripts) (stdlib only, no framework) |
| Front-end without a framework | [tools/configurator/web/](../tools/configurator/web), decisions in [docs/UI-NOTES.md](UI-NOTES.md) |
| Test and verification design | `make verify`, [scripts/selftest-configurator.py](../scripts/selftest-configurator.py) (14 behavioural checks) |
| CI/CD | [.github/workflows/](../.github/workflows) - verify, build, configurator |
| Hardware debugging and recovery | [docs/SCREEN.md](SCREEN.md), [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Technical writing | the docs set, and the measured claims inside it |

## Three things worth asking me about

1. **The constraint.** 1,128 bytes free is not a feature list, it is an exercise
   in deciding what not to ship. The measured costs let me say "this option costs
   4,224 bytes and I want it more than those three" instead of guessing.
2. **The brick.** The display went black but backlit after a mismatched asset
   pack was flashed. Separating mainboard health from display health, finding the
   matching OS image, and writing the recovery down is the part of the project I
   would most want to be asked about.
3. **The harness.** Predicting a compiled size to the byte required measuring
   marginal costs against two baselines, then proving the predictor against real
   builds - and documenting where it is only an approximation.

## Checking it without the printer

- `make verify` - checksums, ARM vector tables, configuration assertions, link
  check, and 14 live checks against the configurator service.
- `./scripts/configurator.sh` - the whole build chain, one command.
- Committed binaries in [firmware/](../firmware) and [screen/](../screen) with
  their manifests and MD5s.

## Media

| | |
|---|---|
| ![Configurator](img/configurator-ui.png) | The configurator: 71 features, measured costs, live flash budget |
| ![Result](img/configurator-result.png) | A real build: flash used, prediction, error, RAM, sha256 |
| ![Pipeline](img/build-pipeline.svg) | Configuration to flashed image, every step a script |
| ![Memory map](img/memory-map.svg) | The 256 KiB budget and what eats it |

