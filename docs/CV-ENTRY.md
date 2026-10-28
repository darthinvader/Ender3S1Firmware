# CV entry - Ender 3 S1 firmware factory

Three lengths, all true to the repository. Paste the first block into a CV, the second into
LinkedIn, the third into a skills grid.

## 1. CV block (a role-style entry)

**Ender 3 S1 firmware factory** - personal project, 2026
*Build service for custom Marlin firmware: any upstream checkpoint, any feature selection, verified image and written SD card.*

- Built a local build service (Python standard library HTTP server + vanilla JavaScript UI, no
  framework) that takes any upstream Marlin checkpoint - 28 release tags and branches, fetched on
  demand - applies a 71-feature selection, compiles it, verifies the ARM vector table and produces
  a signed-off image with its manifest.
- Measured the flash and RAM cost of every feature by compiling it on and off (66 of 71 measured),
  which lets the service predict an image size to the byte and refuse selections that cannot fit;
  predictor error on the reference build: 0 bytes.
- Closed the loop to hardware: a FAT32 writer that formats the card, renames the image to an unused
  8.3 name and md5-verifies every copy, for both the mainboard and the display panel.
- Automated quality: pinned upstream commits, committed binaries with checksummed manifests,
  `make verify@BT@ (checksums, vector tables, configuration assertions, link checking, 14 live
  service checks) and three GitHub Actions workflows, all passing.
- Recovered a bricked display panel by isolating a mismatched asset pack; the recovery kit, the
  evidence trail and the calibration record are part of the repository.

*Stack: Python, JavaScript, embedded C configuration (Marlin), PlatformIO, STM32F103, Linux, FAT32/SD, GitHub Actions.*
*Links: github.com/darthinvader/Ender3S1Firmware - live page: darthinvader.github.io/Ender3S1Firmware*

## 2. LinkedIn / profile paragraph

I built a firmware factory for Ender 3 S1-class 3D printers: choose any upstream Marlin checkpoint
(release tag or branch), tick the features you want, and the service compiles it, verifies the image,
tells you exactly how many bytes you have left and writes the SD card for both processors. The
interesting part was making the numbers honest - every feature's cost was measured by compiling it
on and off, so the size prediction is exact on the reference build instead of an estimate. Python
standard library on the server, vanilla JavaScript in the browser, three CI workflows keeping it green.

## 3. One line for a skills grid

Built a local firmware build service (Python, vanilla JS, PlatformIO) that compiles custom Marlin
images from any upstream checkpoint with byte-measured feature costs, verifies them and writes the
SD card.

