# Troubleshooting: the failures this machine actually produced

Every entry below is a fault that occurred on this printer during the work recorded in this repository - not a generic Marlin checklist. Each one is written as: what you see, why it happens, what to do.

Three habits make the rest of this document unnecessary more often than not:

1. **Verify a setting with its own query, not with `M503`.** On this build a full `M503` dump can trigger a watchdog reset, and a reset wipes anything you set but did not save.
2. **Distrust the screen during a mainboard flash.** It is not running the firmware you are replacing.
3. **Judge the first layer by printing it.** Paper tests on this machine walked the Z offset to a value that did not stick.

## Flashing and boot

### The card flashes, nothing changes

**Symptom** - power cycle with the card in, wait a minute, `M115` still reports the old firmware. The file on the card is untouched.

**Cause** - the Creality SD bootloader stores the last filename it flashed and silently skips a repeat of that name. All five early attempts used `firmware.bin`.

**Fix** - use a name that has never been used on this machine. `firmware/flash-filenames.txt` is the record; `scripts/flash-card.sh --next-name` generates one. If a fresh name still does not take, reformat the card (MBR, FAT32, 4096-byte clusters) before trying anything more invasive.

### The printer is silent after a successful flash

**Symptom** - the flash clearly happened (the card file was consumed), but the host gets no reply.

**Cause** - this build runs at **250000 baud**; stock Creality firmware ran at 115200. A host still configured for 115200 sees silence, which looks exactly like a dead board.

**Fix** - reconnect at 250000. Then `M115` must report `Ender3S1-F1-v2`. Silence at 115200 proves nothing.

### The screen is black but backlit

**Symptom** - after a screen flash the panel lights up and stays black.

**Cause** - either the mriscoc `firmware.zlib` (md5 `728a92a835df3f812271dc2be3482fe1`) was flashed, or the asset set does not match the mainboard firmware family.

**Fix** - flash the official Creality V3.1.9 OS together with the matching asset folder, as described in [docs/SCREEN.md](SCREEN.md). Never flash that mriscoc zlib, and never flash `dcboot.bin`.

### The screen shows the logo and live values but no menu

**Symptom** - boot logo, temperature and position numbers update, the knob clicks but nothing opens.

**Cause** - the screen's asset partition is corrupt or holds the wrong asset family.

**Fix** - reflash the asset folder only (mainboard firmware untouched). Check the card format first: MBR + FAT32 + 4096-byte clusters is the number one failure point.

## Bed leveling and the probe

### `Error: Failed to enable Bed Leveling`

**Symptom** - `G29 T` prints an empty grid of dots, and start G-code aborts on `M420 S1`.

**Cause** - the mesh was dropped from RAM (seen after a cancelled print plus several `M500`s). The copy in EEPROM was intact in every occurrence.

**Fix** - reload it, do not re-probe:

```gcode
G29 L0   ; load mesh slot 0 from EEPROM
G29 A    ; activate it
M500     ; persist
M420 V   ; verify: 'Mesh is valid' and 'Bed Leveling ON'
```

If `G29 L0` also reports an empty mesh, the EEPROM slot is genuinely gone and you do need `G29 P1` / `G29 P3 R`.

### The mesh comes out 5x5 although the firmware was built for 7x7

**Symptom** - `G29 T` shows a 5x5 grid after a fresh probe.

**Cause** - the mesh dimension is also stored in EEPROM (the screen exposes it as a mesh setting). A menu change does not survive a reboot unless it is saved, and `M502` resets it.

**Fix** - set 7x7 in the screen's mesh settings, `M500`, then re-probe. After any EEPROM reset, verify the grid size before spending ten minutes probing.

### The back-right mesh points come back as NaN

**Symptom** - points near the back-right corner of the grid intermittently fail to probe.

**Cause** - those points need the nozzle at about X229.8 / Y219.5 against travel limits of 230 / 220: a 0.2-0.5 mm margin, so some touches are missed.

**Fix** - `G29 P3 R` fills the gaps by interpolation, then save. A larger mesh inset would fix it properly, but `C29` (any parameter form) watchdog-resets this build, so use the screen's mesh settings or rebuild the firmware with a bigger inset.

### `G30` refuses a corner with `Z Probe Past Bed`

**Symptom** - a manual corner probe is rejected.

**Cause** - `G30 X Y` positions the *probe*, and the firmware also checks that the *nozzle* stays on the bed. With a probe offset of X-31.80 / Y-40.50 the probe can only reach about X188 / Y179.

**Fix** - probe at the reachable corner (`G30 X185 Y175`), not at the physical corner. Mesh corners and nozzle corners are legitimately different measurements about 45 mm apart.

### A 1.6 mm bed tilt that will not go away

**Symptom** - the mesh shows one corner roughly 1.6 mm off and mechanical adjustment does not help.

**Cause** - plate bow and gantry geometry. The mesh exists to compensate this.

**Fix** - stop chasing it mechanically. Re-tramming reduced this machine's corner spread to 0.033 mm, and the remaining bow is compensated by the 7x7 mesh. Details in [docs/CALIBRATION.md](CALIBRATION.md).

## Watchdog resets

### The board resets while dumping settings

**Symptom** - `M503` or `C29` is followed by a `Watchdog Reset` on the serial line; the host drops to "offline after error"; EEPROM survives.

**Cause** - a firmware-level watchdog on this build during long report paths. Observed six times in one session, always on `M503` or `C29`.

**Fix** - do not use those commands here. Query one setting at a time (`M92`, `M851`, `M593`, `M900`, `M412`). After any unexplained reset, re-check the values you set immediately before it - unsaved settings do not survive a reset.

### A setting silently reverted

**Symptom** - input shaping or a probe offset is back to its default after a reconnect.

**Cause** - the value was set but not saved, and a watchdog reset or power cycle wiped it.

**Fix** - always `M500` after changing a setting, then re-query it to confirm. Treat "I set it earlier" as a claim that needs checking.

### `M593 X48` does nothing

**Symptom** - setting an input shaping frequency without the `F` keyword appears to be accepted but has no effect.

**Cause** - mriscoc's `M593` requires the keyword form.

**Fix** - use `M593 X F48`, `M593 Y F48`, and set axes in separate commands.

## Motion, extrusion and first layer

### The first layer will not stick although the Z offset was paper-tested

**Symptom** - paper test says the nozzle is right; the print shows under-squished or lumpy first-layer patches.

**Cause** - paper thickness is not a measurement of layer adhesion. On this machine paper tests walked the offset to -2.62, where the first layer stopped sticking.

**Fix** - set the offset from print evidence: -3.10 is the value this machine needed. Change it in 0.02 mm steps and judge the printed line.

### Ghosting or ringing on vertical walls

**Symptom** - ripples at a fixed spacing on cube side walls.

**Cause** - frame resonance, and a shaping frequency that is close but wrong.

**Fix** - this machine settled on `M593 X F48 D0.08` and `M593 Y F48 D0.08`, derived by FFT of photographs of printed cube faces. An eyeball sweep was too coarse. `D0.15` left a visible residual at the correct frequency.

Residuals that shaping cannot remove: an X component near 96 Hz (twice 48, which a ZVD shaper cannot cancel) and a second Y mode around 62-66 Hz. Those are mechanical: belt tension, carriage eccentric nuts, or lower outer-wall acceleration.

### Under-extruded walls at high speed

**Symptom** - matte, weak walls on large parts, perfect small prints.

**Cause** - the hotend's melt rate, not the motion settings. Measured ceiling on the stock Sprite hotend: clean through ~9.0 mm3/s, onset of roughness ~10.8, starved at ~12.6 (220 C, 0.45 x 0.2 mm lines).

**Fix** - cap profile speeds at that ceiling rather than raising temperature. Adding linear advance does not create melting capacity.

### Corners bulge or are starved after tuning acceleration

**Symptom** - corner artefacts after motion tuning.

**Cause** - junction deviation replaced classic jerk in this build, so a jerk number copied from an older profile is meaningless.

**Fix** - `M205 J0.02` on this machine. The configurator default `J0.1` is roughly equivalent to jerk 24 and is far too aggressive.

### The filament runs out and the print continues

**Symptom** - the runout sensor does not stop the print.

**Cause** - compiled support for the sensor exists, but `FIL_RUNOUT_ENABLED_DEFAULT` is false, so it starts disabled. Any EEPROM reset turns it off again.

**Fix** - `M412 S1` followed by `M500`, then verify with `M412`.

## Building the firmware

### `SanityCheck.h` aborts the build

**Symptom** - the build stops with an error about `PROUI_EX` and probing.

**Cause** - `MULTIPLE_PROBING` greater than 0 requires `EXTRA_PROBING` to be exactly 1 with the ProUI extended UI.

**Fix** - enable `EXTRA_PROBING 1` next to `MULTIPLE_PROBING 2`. This is one of the two blockers that stopped the v2 build.

### `ICON_ShapingZ` is undeclared

**Symptom** - `proui/dwin.cpp` fails to compile.

**Cause** - with `INPUT_SHAPING_Z` and `SHAPING_MENU` enabled, upstream code references `ICON_ShapingZ`, but upstream only defines the X and Y aliases.

**Fix** - apply [configs/patches/0002-proui-add-ICON_ShapingZ.patch](../configs/patches/0002-proui-add-ICON_ShapingZ.patch), which adds the alias next to the existing ones. Re-check this when pulling a newer upstream.

### The image no longer fits

**Symptom** - the linker reports a region overflow of a few hundred bytes.

**Cause** - the application region is 233472 B and the shipped build already uses 232344 B.

**Fix** - trim before adding. The ladder that worked here: disable `EEPROM_CHITCHAT` and `EEPROM_INIT_NOW` (444 B, and a reflash then no longer wipes calibration). Further candidates with measured cost are in [docs/DESIGN-NOTES.md](DESIGN-NOTES.md).

## Host-side problems

### The host cannot open the serial port at 250000 baud

**Symptom** - the library or host refuses or cannot open 250000 on the CH341 adapter.

**Cause** - some host-side serial stacks only offer standard rates on this adapter.

**Fix** - bridge it: run a PTY at a conventional rate and relay to the printer at 250000 (on this machine that was a small `socat` systemd user service). The printer is not the problem; the host is.

### A firmware upload over USB aborts part-way

**Symptom** - binary file transfer stalls, then the parser is flooded with garbage.

**Cause** - a `.bin` pushed over plain ASCII upload can contain the byte sequence `M29`, which terminates the transfer. The IS build has one at offset 204858.

**Fix** - use binary file transfer (`M28 B1` / the host's firmware-updater plugin), not ASCII upload. When in doubt, use the SD path.

---

[<- Back to the project README](../README.md)
