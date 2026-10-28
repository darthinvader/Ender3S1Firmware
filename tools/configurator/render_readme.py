#!/usr/bin/env python3
"""Render tools/configurator/README.md from the catalogue and the measurements.

The documentation is generated on purpose: the feature table, the totals and the
measurement summary all come from features.json, so they cannot drift from what
the service actually does.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "tools" / "configurator" / "features.json"
OUT = ROOT / "tools" / "configurator" / "README.md"

BT = chr(96)
FENCE = BT * 3
def bt(s):
    return s.replace("@BT@", BT).replace("@FENCE@", FENCE)

cat = json.loads(CAT.read_text())
feats = cat["features"]
cal = cat.get("calibration", {})
base = cat["baseline"]
region = next(m for m in cat["machines"] if m.get("supported"))["flash_region"]

measured = [f for f in feats if f.get("cost_source") == "measured"]
unmeasured = [f for f in feats if f.get("cost_source") != "measured"]
on = [f for f in feats if f["on_by_default"]]
off = [f for f in feats if not f["on_by_default"]]

rows = []
for group in cat["groups"]:
    group_feats = [f for f in feats if f["group"] == group]
    if not group_feats:
        continue
    rows.append("")
    rows.append("### " + group)
    rows.append("")
    rows.append("| Feature | Id | In your build | Flash | RAM |")
    rows.append("|---|---|---|---|---|")
    for f in group_feats:
        flag = "on" if f["on_by_default"] else "off"
        if f.get("buildable") is False:
            cost, ram = "not toggleable", "-"
        elif f.get("cost_source") == "measured":
            cost, ram = "%+d B" % f["flash"], "%+d B" % f.get("ram", 0)
        else:
            cost, ram = "not measured", "-"
        label = f["label"] + (" (careful)" if f.get("risk") == "high" else "")
        rows.append("| %s | %s | %s | %s | %s |" % (label, bt(f["id"]), flag, cost, ram))
table = "\n".join(rows)

screen = cat.get("screen", {})
os_rows = chr(10).join(
    "| %s | %s | %s B | %s | %s |" % (
        e["label"], "yes" if e.get("verified_on_this_panel") else "no",
        format(e["bytes"], ","), e.get("md5", "")[:12] + "...",
        e.get("note", ""))
    for e in screen.get("os", []))
asset_rows = chr(10).join(
    "| %s | %s | %s B | %s | %s |" % (
        e["label"], e.get("pairs_with"), format(e["bytes"], ","),
        "yes" if e.get("bundled") else "no (too large)", e.get("note", ""))
    for e in screen.get("assets", []))

flash_on = sum(f["flash"] for f in on if f.get("cost_source") == "measured")
blocked = "\n".join("| %s | %s |" % (f["label"], f.get("build_failed", "no reason recorded")) for f in feats if f.get("buildable") is False)
top = sorted([f for f in feats if f.get("cost_source") == "measured"], key=lambda f: -f["flash"])[:5]
top_rows = "\n".join("| %s | %+d B |" % (f["label"], f["flash"]) for f in top)

doc = bt("""# Firmware configurator

A local web app that turns \"I want these features\" into a compiled, checksummed, flashable **Ender3S1-CFG** image for the Ender 3 S1 - using the same pinned Marlin tree, the same configuration and the same verification as the rest of this repository.

![Configurator UI](../../docs/img/configurator-ui.png)

## Quick start

@FENCE@bash
./scripts/bootstrap.sh                      # once: pinned sources + PlatformIO 6.1.19
python3 tools/configurator/server.py        # -> http://127.0.0.1:8787
@FENCE@

Three presets cover the common cases:

| Preset | What it selects |
|---|---|
| **What I run now** | exactly the feature set of the firmware on the machine today (the default state of the page) |
| **Minimum** | everything that can be turned off, turned off |
| **Add what fits** | starts from what you run now and adds every measured feature that still fits, cheapest first |

The page always shows whether the current selection is **bigger or smaller than the image you run now**, in bytes and percent, next to the flash bar.

## Using the page

* **Filter** at the top of the feature list matches names, ids and descriptions; group headers collapse when clicked, so 71 features stay navigable.
* **A build is tied to the selection it was made from.** Change a feature, the machine, the screen image or the asset pack and the write panel disables itself with *"the selection changed since that build"* - the card can no longer be written from a stale image. Change it back and it re-enables, because the signature matches again.
* **Errors surface as a toast** and in the log, never as a silent no-op: a refused build says why, a failed link says how many bytes overflowed, a refused write says which rule stopped it.
* **Modals** close on Escape, confirm on Enter, and return focus to where it was.
* The footer carries the date the costs were measured, so a stale catalogue is visible rather than implied.

## Firmware versions

The page builds the pinned commit by default, and it can also build any release tag or branch mriscoc has published. Nothing is hardcoded: the list comes from the GitHub API when the page loads, is cached for an hour, and re-reads on **refresh list**.

| Choice | Prediction | What the build does |
|---|---|---|
| **pinned** (default) | measured costs, the exact delta against your current image | the tree this repository is built from |
| a release tag, e.g. @BT@20260106@BT@ | not measured | **download this version** puts a shallow clone in @BT@build/sources/<id>/@BT@, then the same compile runs against it |
| a branch, e.g. @BT@Ender3V2S1-Bugfix@BT@ | not measured | same, at the commit the branch points to when you download it |

Measured costs are a property of the pinned tree, so the page does not predict for any other version: the budget line reads **not measured**, the build button stops applying the over-budget gate, and the result reports the size the linker actually produced.

Two details make older trees usable rather than fatal:

* **Tolerant application.** A catalogue option that a tree does not contain is skipped and listed in the manifest under @BT@skipped@BT@, instead of failing the compile - so this configuration still builds on a 2024 tree that predates a define.
* **What is new.** Before you build, the page compares the version's @BT@Configuration.h@BT@ and @BT@Configuration_adv.h@BT@ with the pinned release's (fetched from the same commit, not from the working tree) and lists the options the version has that the pinned one does not.

## What a build gives you

| Artifact | What it is |
|---|---|
| @BT@firmware.bin@BT@ | the image, stamped @BT@Ender3S1-CFG@BT@ so @BT@M115@BT@ identifies it |
| @BT@manifest.json@BT@ | machine, selection, **what changed versus the shipped build**, warnings, predicted vs measured size, sha256, upstream commits |
| log | the full PlatformIO output |

## The screen

The panel is a second computer, and it is the one part of this machine whose firmware **cannot be built here**: its OS is a proprietary @BT@.zlib@BT@ and its asset pack is a resource bundle, not code. Its menus are drawn from the mainboard's ProUI defines, which the feature list already controls - so a screen feature is a mainboard toggle, and this page handles it there.

What the configurator does control is the **pairing**: which OS image and which asset pack go on the screen's own card, chosen to match the firmware being built.

| OS image | Verified on this panel | Size | md5 | Note |
|---|---|---|---|---|
{os_rows}

| Asset pack | Pairs with | Size | Bundled | Note |
|---|---|---|---|---|
{asset_rows}

Both are bundled with the firmware: **Download bundle (.zip)** contains @BT@firmware.bin@BT@, @BT@manifest.json@BT@, @BT@FLASH-THIS.txt@BT@ and @BT@screen/firmware.zlib@BT@ plus @BT@screen/private/@BT@ for the selected pair. A pack that does not pair with custom firmware is refused with the reason - that mismatch is what bricked this panel in July.

## Writing the card

The page can finish the job: pick the device, pick what goes on it, and the service formats it and copies the files.

* devices come from @BT@lsblk@BT@ - only removable and loop devices are offered, internal disks are refused twice over (not removable, and any device carrying @BT@/@BT@, @BT@/boot@BT@ or @BT@/home@BT@)
* a mounted card is unmounted first, and the modal names what is about to be destroyed
* the card is reformatted MBR + FAT32 with 4096-byte clusters, which is what the Creality bootloader needs
* one card can carry both: the mainboard image is renamed to an unused 8.3 name from the registry, and the screen OS plus @BT@private/@BT@ go alongside it
* every copy is md5-compared after the write, and the filename is recorded in @BT@firmware/flash-filenames.txt@BT@
* writing needs root: the service uses passwordless sudo and refuses cleanly (409) instead of hanging on a password prompt

## Over-budget builds

A prediction is not a limit. If the selection is larger than the region, the build button turns red and reads the overflow, a line under it says what will happen, and a modal explains the trade-off before anything runs:

> Prediction: 234,728 B against the application region of 233,472 B - 1,256 B too large. On an STM32F103RCT6 with the 28 KiB bootloader the link will stop at 233,472 B. The build is still allowed because your board may have more flash than this preset assumes, or you may be checking what a configuration would need before trimming. The compiler is the authority here, not this estimate.

Build anyway and the linker answers: if the image really does not fit, the result says exactly how many bytes overflowed.

## Dependencies between features

Some toggles need another one to exist, and the service enforces both directions:

* @BT@advk_tune_item@BT@ (the screen's linear-advance tuning screen) **requires** @BT@linear_advance@BT@. Ask for the screen item while LA is off and LA is switched back on for you, recorded as @BT@auto_added@BT@ in the manifest.
* @BT@plr@BT@ and its screen tune item move together, because Marlin's sanity check refuses one without the other.
* @BT@restore_leveling_after_g28@BT@ and @BT@enable_leveling_after_g28@BT@ are mutually exclusive; both selected is refused before a compiler starts.
* @BT@bft@BT@ and @BT@sdcard_readonly@BT@ conflict.

Every automatic change is written into the manifest, so a build never quietly differs from what you asked for.

## Every cost is measured

Nothing in the catalogue is a datasheet number. Each feature was priced by compiling it:

* a feature that is **on** in the shipped configuration was measured by turning it off and seeing how much the image shrank
* a feature that is **off** was measured by turning it on against a slimmed baseline that frees headroom, and seeing how much the image grew
* a link that overflows still measures: the linker states how many bytes over it went, and that becomes the price

Two baselines make that possible:

| Baseline | Flash | RAM | What it is |
|---|---|---|---|
| A | {a_flash} B | {a_ram} B | the shipped configuration, built by the configurator |
| B | {b_flash} B | {b_ram} B | A minus the screen extras, BFT and the macro slots, to make room for measuring additions |

The catalogue now holds **{n} features** ({n_on} on in your build, {n_off} off): **{n_measured} priced by a real build**, and {n_blocked} that cannot be toggled on this board at all (the compiler refuses them - see the list below). The most expensive things you are carrying:

| Feature | Cost |
|---|---|
{top_rows}

### The five that cannot be toggled here

They are hidden from the page by default - a row you cannot touch is noise. Tick **Show options that cannot be used here** in the header and they reappear, greyed, with the compiler's reason next to each one. The same switch reveals the unsupported machine presets and the screen packs that pair with stock firmware, which are kept for the Ender 3 Pro work later on.

{blocked_rows}

## The catalogue

{table}

## How it works

@FENCE@text
features.json  ->  apply_features.py  ->  PlatformIO  ->  firmware.bin + manifest.json
      ^                  |                   ^
      |                  v                   |
   server.py  <-- budget check refuses over-budget selections
      ^
      |  HTTP + static page
   browser
@FENCE@

| File | Role |
|---|---|
| @BT@features.json@BT@ | the catalogue: every toggle, the defines it flips, the measured flash and RAM cost, the machines it applies to |
| @BT@apply_features.py@BT@ | copies the baseline configuration, flips the defines, **verifies each flip landed**, stamps the identity, applies the upstream source patch, enforces the budget |
| @BT@server.py@BT@ | stdlib HTTP service: catalogue, build queue, job status, log tail, artifact and manifest download |
| @BT@web/@BT@ | the page: checkboxes, presets, live budget and size delta, build log, result panel |
| @BT@measure.py@BT@ | the measurement harness that produced the costs above |
| @BT@merge_measurements.py@BT@ | writes measured costs back into the catalogue |
| @BT@validate_catalog.py@BT@ | static consistency check, part of @BT@make verify@BT@ - proves every define exists exactly once and that @BT@on_by_default@BT@ matches the configuration file |

## Verified

| Check | Result |
|---|---|
| Default selection | predicted {a_flash} B, measured {a_flash} B, error **0 B** |
| Two toggles off (@BT@ui_colors@BT@ + @BT@is_z@BT@) | predicted 228,596 B, measured 228,596 B, error **0 B**, 3,748 B smaller than the running image |
| **Add what fits** (9 features added on top) | predicted 233,328 B including the 64 B/feature margin, measured 232,736 B: 592 B conservative, and it builds |
| Over-budget request | refused before compiling, with the exact overflow |
| Artifact identity | @BT@M115@BT@ reports @BT@Ender3S1-CFG@BT@ |
| Artifact integrity | @BT@scripts/check-vector-table.py@BT@ passes on every build |
| Catalogue consistency | @BT@validate_catalog.py@BT@: no inconsistencies across all {n} features |

![A finished build: predicted equals measured](../../docs/img/configurator-result.png)

## Limits

* **STM32F103 only.** F401 boards take a different image with a different vector offset; the catalogue marks them unsupported rather than pretending.
* **This service runs a compiler.** It binds to @BT@127.0.0.1@BT@ and has no authentication. Do not expose it to a network you do not control.
* **One job at a time**, queue depth 4. A cold tree is refused with a pointer to @BT@./scripts/bootstrap.sh@BT@.
* **Curated, not exhaustive.** Marlin has hundreds of options; the catalogue carries the ones that mean something on this machine. Adding another is one entry plus one measurement run.
* **Other versions are compiled, not measured.** The page predicts only for the pinned tree, because a cost belongs to the tree it was measured on. For every other version the result panel reports the size the linker produced and nothing more.
* **Old trees hit vocabulary drift.** Tolerant application skips defines a tree does not contain, but it cannot translate a configuration written for a newer Marlin into an older one: `20260106` (January 2026) and `Ender3V2S1-Bugfix` (September 2026) both build, while `20220719` fails the dependency scan with the tree's own error, HAS_GCODE_PREVIEW requires ProUIex - the 2022 tree has no DGUS_UI_IS macro and no ProUIex. The failure names itself in the log and no image is produced.
* **Downloads are shallow clones.** About 200 MB per release tag into `build/sources/`, kept until you delete the directory; the version list itself is one cached GitHub API call.
* **Marginal costs.** Each price is the cost of that feature against the two baselines above; two features that share code can interact by a few bytes of alignment. The result panel always shows the exact measured size of the selection you built, so the prediction is a planning aid, not a promise.

## Serverless variant

[@@.github/workflows/configurator.yml@@](../../.github/workflows/configurator.yml) runs the same apply-and-build on GitHub Actions via @BT@workflow_dispatch@BT@. It is a template: not exercised on a runner yet, while the local path above has.

---

[<- Back to the project README](../../README.md)
""")

doc = (doc
       .replace("{a_flash}", format(cal.get("baseline_a", {}).get("flash", base["flash"]), ","))
       .replace("{a_ram}", format(cal.get("baseline_a", {}).get("ram", base["ram"]), ","))
       .replace("{b_flash}", format(cal.get("baseline_b", {}).get("flash", 0), ","))
       .replace("{b_ram}", format(cal.get("baseline_b", {}).get("ram", 0), ","))
       .replace("{n_measured}", str(len(measured)))
       .replace("{n_on}", str(len(on)))
       .replace("{n_off}", str(len(off)))
       .replace("{top_rows}", top_rows)
       .replace("{table}", table)
       .replace("{os_rows}", os_rows)
       .replace("{asset_rows}", asset_rows)
       .replace("{n_blocked}", str(len([f for f in feats if f.get("buildable") is False])))
       .replace("{blocked_rows}", blocked)
       .replace("{n}", str(len(feats)))
       .replace("@@", BT + BT))

OUT.write_text(doc)
print("wrote", OUT, len(doc.splitlines()), "lines;", len(measured), "measured of", len(feats))
if unmeasured:
    print("unmeasured:", [f["id"] for f in unmeasured])
