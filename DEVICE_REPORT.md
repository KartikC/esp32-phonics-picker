# Physical-device verification snapshot

This is a sanitized record of the production build tested on a physical
Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 on 2026-08-22. Per-device identifiers,
local serial paths, private factory backups, and raw microphone captures are
intentionally excluded from the public repository.

## Hardware observed

- ESP32-S3 QFN56 rev 0.2, dual-core 240 MHz
- 8 MB embedded PSRAM and 16 MB flash
- physical V2 display/touch revision: CO5300 + CST820
- live I2C devices at `0x15`, `0x18`, `0x20`, `0x34`, `0x51`, `0x6B`, and
  `0x7E`

The observed CST820 at `0x15` and CO5300 panel agree with Waveshare's V2
documentation. Older seller listings describing SH8601 + FT3168 refer to V1
and are not compatible with this firmware.

## Installed build evidence

- source: `firmware/PhonicsGame/`
- Arduino-ESP32: `3.3.11`
- Waveshare source commit: `7ab8f957e22ea1ab811256359f4eddcaaf49ee91`
- accepted audio-pack SHA-256:
  `563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`
- every written flash region passed esptool's post-write verification
- the runtime reported 8 MB PSRAM, ready audio at logical volume 100, a ready
  QMI8658 IMU, two distinct choices, and no preview mode
- 131,072 seeded rounds plus focused state-flow tests passed; targets and
  distractors always differed, and C/K never opposed one another
- exhaustive geometry tests covered all six layouts, both pulse sides, the full
  motion range, display bounds, card separation, and replay-target clearance

## Human-observed behavior

- the display showed exactly two distinct readable lowercase cards, one fixed
  replay control, tiny battery dots, a pure-black unused canvas, and no answer
  or instructional header text
- the full frame remained buffered: no clearing, partial drawing, or animation
  intermediates were visible on the AMOLED
- both cards followed physical tilt in portrait orientation, with a subtle
  independent easing lag while remaining within their original hit regions
- replay produced the current prompt and target phonics sound through the
  onboard speaker
- wrong answers retained the round; correct answers produced the bounded pulse
  and advanced after praise
- a short physical PWR press/release entered standby and woke to the same round
  with audio ready
- the AXP2101 battery indicator was visible as three green dots at full charge

Human listening accepted the checked-in gentle 16 kHz audio path. Automated
hashes and serial status catch missing or corrupt data, but do not replace
listening on the physical speaker.

## Installed audio evidence

- 26 phonics sounds and 16 spoken cues (42 assets total)
- 16 kHz, mono, signed 16-bit PCM
- 954,220 bytes of WAV files; 950,976-byte raw packed payload
- 29.713 seconds total authored audio
- packed at the `ffat` partition offset `0x610000`
- all accepted WAV hashes, pack offsets, payload bytes, and the firmware index
  are checked by `scripts/verify_repo.py`

The public deployment path rebuilds the application from pinned sources and
flashes this same checked-in audio pack. A successful build alone is not a new
physical-device verification; use `scripts/verify_device.py` and repeat the
manual checks in `AGENTS.md` after flashing another unit.

## 2026-08-24 creature-reward and maintenance-mute update

The same physical V2 board was updated through the canonical five-region flash
path. Esptool identified an ESP32-S3 QFN56 rev 0.2 with 8 MB PSRAM and 16 MB
flash, then hash-verified every written region. The installed application is
899,776 bytes with SHA-256
`8968c755c98a698ca56593da98a1c1d9b7bb31dda5e805870e377a1733b3a28a`.
The checked 950,976-byte audio pack and its hash are unchanged.

The final serial verifier reported ready audio at logical volume 100, a ready
IMU, 8 MB PSRAM, an awake non-preview game, USB data present, and two distinct
choices. Its forced common reef shark and rare royal-diamond seahorse both
completed while the diagnostic rarity counters remained `clean=0` and
`pity=0`. Cleanup left `audio=ready`, `mute=off`, and `preview=no`.

An Insta360 Link 2C camera and its microphone recorded the physical AMOLED
during a second deterministic sequence:

- common Tide-slate striped giant octopus;
- rare Kelp-green royal-diamond seahorse;
- USB maintenance mute on and off; and
- the normal card screen before, between, and after those states.

The 46.866-second original is stored locally at
`build/device-verification/esp32-creature-reward-verification-insta360.mov`
(71,290,115 bytes, SHA-256
`4db1c5c15593a1252748fd247818d3dd7ede178b8269900fef34795b6532395b`).
A 22-second review copy is stored beside it as
`esp32-creature-reward-verification-trimmed.mp4` (2,610,567 bytes, SHA-256
`4ea4d0a0fb45ad06d962dc64b765319e9718a2ee9bd0006d2ac07b9d47d737f9`).
These files remain under the ignored `build/` evidence directory rather than
the public source payload.

Frame-by-frame inspection of the recording confirmed:

- water rises continuously from the card screen, holds one large creature,
  recedes completely, exposes the intended short black beat, and returns to a
  clean next round;
- the octopus occupies most of the display, its stripes remain attached across
  animation frames, and its blue/cyan ramp does not drift to purple;
- the rare seahorse is tall and centered, with the pale-green treatment,
  royal-diamond marks, and rare sparkle visible;
- the former large stationary colored circles at the lower corners are absent;
- the crossed-speaker indicator visibly replaces the replay triangle while
  USB mute is active and the triangle returns after unmute; and
- the saved movie is already unmirrored: the recorded `m`/`v` round agrees with
  the serial target on the right, and the `e`/`z` round agrees with the serial
  target on the left. No horizontal flip was applied.

The saved movie contains a 44.1 kHz mono AAC microphone track. Recorded speech
bursts align with both forced rewards; its measured peak is -22.6 dBFS, so it
is present and unclipped. This run did not substitute camera evidence for the
remaining hands-on gates: physical double-tap timing, sustained cable-removal
auto-unmute, touch alignment, tilt response, standby/wake, and a fresh
perceptual listening pass still require a person at the board.

## 2026-08-24 eight-creature production reward completion

This later append-only entry supersedes the installed application identity in
the preceding creature-reward entry. The earlier entry remains the historical
record for the four-creature build and camera sequence tested at that time.

The same confirmed V2 board was updated with the canonical five-region path.
Esptool identified the ESP32-S3 rev 0.2, 8 MB PSRAM, and 16 MB flash before it
hash-verified the bootloader, partition table, OTA selector, application, and
audio pack. The installed application is 1,318,976 bytes with SHA-256
`cfc5e72c1cd9028bd3c1f8c19c809bebf78b61b2db89d6482f6033375832e44f`.
The unchanged 950,976-byte audio pack retained SHA-256
`563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`.

The installed creature data is tied to these source artifacts:

- variation manifest SHA-256
  `d00bce8ea5843a27183887268c4b3c196753752c65e42ae8fe5ebf7592d9d9b4`;
- generated runtime header SHA-256
  `fee6fef6f60b5bf1d869b0f0d693ac3dd3574ee4281cbcd10b738d70393891c3`;
  and
- variation report SHA-256
  `83ca1cf253accea4b1dd2b0369d8220a11eebcc0cc7f476d06c553b6f8ae7e0e`.

The report contains eight creatures, 32 complete frames, six palettes, zero
protected-pixel changes, and 836,832 packed bytes. The production and separate
ocean-demo firmware targets both compiled. The separate eight-creature ocean
demo was not flashed during this run; this entry verifies the production
PhonicsGame consumer.

The final `scripts/verify_device.py` run passed with 8 MB PSRAM, ready audio at
logical volume 100, a ready IMU, USB data present, an awake non-preview game,
and distinct choices. It completed one timed common glass-squid reward and one
timed rare Ghost-current eel reward, then invoked the exact production renderer
for normal and authored-rare forms of all eight species. Glass squid and sea
angel stayed within Tide slate, Kelp green, and Moon pale; Plum deep remained
excluded from automatic selection. Diagnostic rarity counters stayed at
`clean=0` and `pity=0`. Cleanup and a later post-camera status check both left
`audio=ready`, `mute=off`, `preview=no`, and the normal game visible.

Two later Insta360 recordings provide current-build visual evidence:

- `build/device-verification/eight-creature-animation-insta360.mov` is
  88.912 seconds and 134,523,175 bytes, SHA-256
  `28b621bd19f85f15a6a528467d48b012ea22a50e3a3f54438f9850b9b94df537`;
  it records the production renderer looping reef shark, anglerfish, rare
  Prismatic-panes glass squid, rare Halo-wings sea angel, and rare
  Ghost-current deep-sea eel;
- `build/device-verification/eight-creature-transition-insta360.mov` is
  31.933 seconds and 48,086,137 bytes, SHA-256
  `881830c0b860d3d263891ad79254272065cf856a2f2a290c003fd76ef40bf018`;
  it records real common glass-squid and rare Royal-diamonds seahorse reward
  transitions from cards through the next clean rounds.

Both are 1620 x 1080 H.264 at 30 fps with a 44.1 kHz mono AAC microphone
track. The transition recording's measured audio peak is -23.2 dBFS, present
and unclipped. Photo Booth's live preview was mirrored, but both exported
movies are already unmirrored: device text reads normally and no horizontal
flip was applied. The files and derived contact sheets remain in the ignored
`build/` evidence directory.

Frame-by-frame inspection of those exports confirmed:

- the real reward rises from the two-card screen, displays one large creature
  for the longer hold, recedes completely, and returns to a fresh round;
- the small centered `Glass squid` name remains legible through the final
  creature-visible recede frames and disappears for the terminal black beat;
- the glass squid remains pale and translucent-looking rather than drifting to
  the rejected purple treatment, with its eyes and internal anatomy protected;
- the shark visibly cycles closed / half / open / half jaw silhouettes with a
  synchronized forward lunge, stable eye and gills, and no generated teeth;
- the attached angler lure visibly cycles warm dim / medium / bright / medium
  while its head hovers and tail paddles;
- the glass-squid mantle and arms pulse, the sea-angel wings beat without
  detached celebration sparkles, and the eel body undulates while its head
  stays visually stable; and
- the recorded seahorse remains tall and centered with its rare royal-diamond
  marks, while the current label plaque and water scene remain readable.

Automated serial and camera evidence do not substitute for the remaining
person-at-device gates. Physical replay-circle double-tap timing, sustained
cable-removal auto-unmute, touch alignment, tilt response, standby/wake to the
same round, and a fresh perceptual speaker-listening pass remain pending.

## 2026-08-24 exhaustive production creature catalog and game walkthrough

This append-only entry supersedes the installed application identity in the
preceding eight-creature entry. The visual assets are unchanged; the later
application adds only a USB-data diagnostic command that requests an exact
allowed creature, palette, common pattern or authored-rare treatment, and
representative seed. Production reward selection and child-facing behavior are
unchanged.

The same previously approved `/dev/cu.usbmodem1401` V2 board was flashed again
through the canonical five-region path. Esptool identified the ESP32-S3 rev
0.2, 8 MB PSRAM, and 16 MB flash, then hash-verified the bootloader, partition
table, OTA selector, application, and unchanged audio pack. The final
application is 1,337,952 bytes with SHA-256
`868b566141aaf4a7e215599ab6f9b62f1df65ea3c5a0a01fa0faad489c2e7b26`.
The 950,976-byte audio pack remains SHA-256
`563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`.

The new exact command was first smoke-tested on the physical board with an
allowed Moon-pale spotted glass squid. The same command rejected Plum deep for
that species. The unattended catalog driver then received and validated an
exact acknowledgement for every requested combination:

- 144 common variants: every production-allowed palette crossed with solid,
  spots, stripes, and mottle;
- 36 authored-rare variants: every production-allowed palette crossed with
  the species-specific rare motif;
- 25 combinations each for moon jelly, reef shark, giant octopus, seahorse,
  anglerfish, and deep-sea eel; and
- 15 combinations each for glass squid and sea angel, restricted to Tide
  slate, Kelp green, and Moon pale.

This is the complete finite categorical matrix of 180 variants. Procedural
texture placement accepts a 32-bit seed, so an infinite visual-seed sequence
cannot be enumerated; the catalog deliberately uses one deterministic
representative seed per categorical combination. Plum deep appears zero times.
Each recorded segment is 1.5 seconds, covering more than three complete 440 ms
four-frame loops. Catalog start and end status both reported 8 MB PSRAM,
`audio=ready`, `imu=ready`, `preview=no`, `mute=off`, USB data present, and
unchanged rarity counters `clean=0`, `pity=0`.

The untouched Photo Booth export is
`build/device-verification/final-all-creature-modifiers-insta360.mov`:
358.714 seconds, 541,611,643 bytes, 1620 x 1080 H.264 at approximately 30 fps
with 44.1 kHz mono AAC, SHA-256
`38f2c87f96cb5aff6b4119499a5c3a2da740eaf18f0c48d7a9b46a74bc1cc22b`.
The serial timeline SHA-256 is
`0720a66ad37e780c1d61206cb572ea0844ff538583563ba54ce18fdacdbd2c4b`.
The saved movie is already unmirrored; animal names read normally, and no
horizontal flip was applied.

Derived review artifacts preserve the untouched master and live under the
ignored `build/device-verification/` evidence directory:

- the fully labeled 180-entry review reel is 52,741,446 bytes, SHA-256
  `e84c1e80df68ad284692c2100aa55eb41c3828b21ce9029912b2c351f9da2288`;
- the eight per-species animated review clips and eight exhaustive contact
  sheets are individually hashed in
  `final-all-creature-modifiers-evidence.json`;
- the quick 8 x 5 modifier-axis overview contact sheet is 2,027,315 bytes,
  SHA-256
  `1dcef6312d881a5b539214d490c82fc502fb5cd0528a501ef2744fc0f6c3d895`;
  and
- `final-all-creature-modifiers-index.tsv` maps all 180 ordinal labels to raw
  video timestamps, exact commands, seeds, and serial acknowledgements; its
  SHA-256 is
  `c6338abeb80f6cd3d5c4cd21278803be8214d344aaf02226fa44ba93968e5185`.

A second raw Photo Booth export records a representative real game walkthrough:
replay of target `n`, a genuine wrong choice, replay of the retained `a`/`n`
round, a genuine correct choice, a Tide-slate mottled glass-squid reward, and
the fresh `s`/`e` round. It is
`build/device-verification/final-game-walkthrough-insta360.mov`, 38.931
seconds, 58,963,307 bytes, SHA-256
`67783f1b6bd38c564390c7cc3d9c02e6e07d99e8a02fcb7fc2cb26387fe2929e`.
Its microphone track is present and unclipped, with measured mean -52.3 dBFS
and peak -24.0 dBFS. The serial timeline SHA-256 is
`ee225d80972961b2364c271dcd9ab3851817c06b44aeedaf123645f220c4a8c9`.

Serial-aligned frame inspection confirms the correct pulse at 0-400 ms, water
rise at 400-640 ms, creature and centered name beginning at 640 ms, the
full-water hold through 2560 ms, recede through 2840 ms, the intended fully
black beat through 2960 ms, and the fresh next round. The labeled 17.967-second
review clip is SHA-256
`fbcdc20485c4f74b2c878b6f72139ca3244d769eb604c6adaacd0795e8dd7945`;
the eight-frame timing sheet is SHA-256
`442bcbbbba85c4f5a2cffd295cd531096c50cbc7c50ed41370c995cecb97ab5b`.
Camera rolling shutter blends one boundary frame, but the black display beat
is present before the next round.

An independent final `scripts/verify_device.py` pass again exercised timed
common and rare rewards, all eight common render paths, all eight authored-rare
paths, palette restrictions, serial mute/unmute, audio, PSRAM, IMU, and cleanup.
The walkthrough naturally advanced progress to `clean=1`, `pity=1`; the final
verifier left both counters unchanged and returned the board to
`audio=ready`, `mute=off`, `preview=no`, and the normal game. Photo Booth was
restored to its live Insta360 view.

This closes the requested on-device creature/modifier catalog and visual game
timing confirmation. It still does not substitute for a person's physical
touch-alignment, replay-circle double-tap timing, sustained cable-removal
auto-unmute, hand-tilt, PWR standby/wake, or perceptual speaker-quality checks.

## 2026-08-24 power-efficiency pass

This append-only entry supersedes the installed application identity above.
It keeps the same child-facing pixels, brightness, motion rate, volume, audio
assets, game timing, and eight-creature reward pack while removing avoidable
awake-silent and standby work.

The same previously approved `/dev/cu.usbmodem1401` V2 board was flashed through
the canonical five-region path. Esptool identified ESP32-S3 rev 0.2, 8 MB
PSRAM, and 16 MB flash, then hash-verified the bootloader, partition table, OTA
selector, application, and unchanged audio pack. The installed application is
1,339,184 bytes with SHA-256
`4895b32390e09538b5ed7a932e92c5c5d7e92b5a9a5f0af9a14832c5712a9c61`.
The 950,976-byte audio pack remains SHA-256
`563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`.

The installed power changes are deliberately bounded:

- the unused I2S receive/microphone channel is no longer allocated;
- after the final authored 40 ms gap and another 750 ms of silence, the ES8311
  is muted and powered down, the NS4150B amplifier is gated, and I2S transmit
  is disabled; the next cue restores muted clocks and primed silence before
  enabling the amplifier and unmuting;
- native CST820 `TP_INT` gates idle touch I2C reads, with the original 8 ms
  cadence retained through contact and release, a 64 ms missed-edge safety
  poll, and continuous polling as the fail-safe if interrupt setup fails; and
- awake PWR expander reads run every 20 ms instead of every 8 ms, remaining
  comfortably inside the unchanged 50 ms debounce contract.

The final device verifier required `touch_irq_gate=yes`, proved an audio
`idle -> on -> idle` cycle and an incremented idle-shutdown counter, checked the
reduced touch and PWR cadences, distinguished maintenance mute as
`audio_power=suspended`, and again exercised both timed rarity paths plus all
eight common and eight authored-rare renderers. Cleanup returned the normal
game with `mute=off`, `preview=no`, and `audio_power=idle`.

A second representative game walkthrough drove replay, a genuine wrong choice,
replay, a genuine correct choice, a large Kelp-green spotted Moon Jelly reward
with its centered name, and the fresh `c`/`f` round. The serial timeline began
with `audio_idle_downs=12` and ended at `17`, exactly one completed idle
shutdown for each of its five spoken sequences. It is
`build/device-verification/power-efficient-game-walkthrough-timeline.json`,
SHA-256
`f8e3d2cd3ecd75b782f66ddb4cf2c3aaf6b3fd3381b9ca6d0d13170a96672862`.

The untouched Photo Booth/Insta360 master is
`build/device-verification/power-efficient-game-walkthrough-final-insta360.mov`:
58.075 seconds, 88,024,613 bytes, 1620 x 1080 H.264 with 44.1 kHz mono AAC,
SHA-256
`416c875050681fcc0bc920850711245d16df97ea4574c5e6d04f7326db803797`.
The short review copy is
`power-efficient-game-walkthrough-final-review.mp4`, SHA-256
`1b58c996c6d872192f2e634100afa6b9fcce087546ddaddd8a88e8a4a38d7bb4`.
Frame inspection confirmed the same readable cards, animated water,
full-screen creature and centered label, black transition beat, and next-round
presentation. The contact sheet is SHA-256
`8ae50ed298f05aebc71f156ea8c1fc907770ee26f14d67a6b866ca1336c43c00`.

The camera microphone track is present and unclipped: mean -51.2 dBFS and peak
-23.6 dBFS. Timeline-aligned 20 ms waveform inspection and a 34-54 second
spectrogram found all five expected cue groups and no isolated full-scale or
broadband transient at the inferred wake or shutdown boundaries. The
spectrogram is SHA-256
`3e4b6fef6bb7f76af1da0a43bbbd64004067ebbb91e0178576ae22e890753887`.
This supports the absence of an obvious camera-recordable pop or clipped cue;
it does not replace a person's listening judgment at the onboard speaker.

No power percentage or milliamp figure is claimed. This run used an attached
USB data host, so standby intentionally retained awake PWR polling to protect
USB Serial/JTAG; it did not exercise the battery/charge-only 50 ms light-sleep
branch. Remaining physical gates are an inline whole-board current comparison,
battery/charge-only short-PWR wake and 100-cycle testing, hands-on touch and
tilt, replay-circle double-tap/cable removal, and a final human listening pass.

## 2026-08-24 selected shark and octopus refresh

This append-only entry supersedes the installed application and the reef-shark
and giant-octopus visual evidence above. It deliberately does not repeat the
other six unchanged creatures or the game walkthrough. The selected reef shark
is now the screen-filling, foreshortened three-quarter banking pose from Retro
Diffusion seed `82412`, with a reviewed source-conditioned four-frame chomp.
The giant octopus retains its existing silhouette and motion while replacing
the oversized dark patch behind its eye with a mantle-tone shadow.

The same previously approved `/dev/cu.usbmodem1401` V2 board was flashed through
the canonical five-region path. Esptool identified ESP32-S3 rev 0.2, 8 MB
PSRAM, and 16 MB flash, then hash-verified the bootloader, partition table, OTA
selector, application, and unchanged audio pack. The installed application is
1,427,872 bytes with SHA-256
`7133805d7b899392c40cdb5afb90d54eca39133d934b7582f26467d042e1df18`.
The 950,976-byte audio pack remains SHA-256
`563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72`.
The post-flash device verifier passed with 8 MB PSRAM, ready audio at logical
volume 100, a ready IMU, USB data present, and maintenance mute returning off.
It exercised both timed rarity paths and all eight common and eight
authored-rare render paths, then restored the normal game with `preview=no`.

The installed creature payload is tied to these reviewed artifacts:

- the variation manifest is SHA-256
  `6f6a3e66a2679b6af3a3dd428b5b5978f648e037f1e788a52f2df2256faa4c4f`;
- the generated runtime header is SHA-256
  `25819482f645bedbf92c0fafa80984755a9699fab1fb7f10a928b5e291666df7`;
- the passing variation report is SHA-256
  `5a972b1a522236531d89892b4b666af358b23408c3a244cd6988fac01f952da9`;
- the exact selected `82412` source PNG is SHA-256
  `0042e78252174923e339f3bf0f29d1b083bd26d9a0eddc0a4e80c91629e58c7c`;
  and
- the reviewed closed / half-open / open / half-open shark sheet is SHA-256
  `78a3f778aa1cf943e41b01081e87ede44b70e4229086a74edfbcb820745c4f7a`.

A focused Insta360 capture and deterministic USB timeline cover exactly the
two changed species. The 50-entry matrix contains 40 common variants and 10
authored-rare variants: for each species, every one of its five allowed
palettes is crossed with solid, spots, stripes, mottle, and its rare motif.
Each acknowledged segment lasts 1.5 seconds, more than three complete 440 ms
animation loops, with one representative deterministic seed per categorical
combination. Start and end status both recorded 8 MB PSRAM, `audio=ready`,
`audio_power=idle`, `imu=ready`, `preview=no`, `mute=off`, USB data present,
and unchanged rarity counters `clean=0`, `pity=0`.

The unmirrored 1920 x 1080 H.264/AAC camera master is
`build/device-verification/shark-octopus-refresh-insta360-direct.mp4`: 105.742
seconds, 134,480,067 bytes, SHA-256
`5741c7a5b02b550b67f041d16f80c2d9a60d0d214b1a2a9d3d3b201bf9a7eaa6`.
Its exact 50-entry serial timeline is
`shark-octopus-refresh-direct-timeline.json`, SHA-256
`2954c59b8549df6b56cd103939af6bf0d8bc32dd961baff0d77e1bc901a6f86c`.
The efficient 600 x 970 mobile review is
`build/device-verification/mobile-drive/ESP32-shark-octopus-refresh-mobile.mp4`:
85.754 seconds and 21,087,342 bytes, SHA-256
`a1c6cbaeea1cc596d4ed9c0f16a611e4520fe5e756fee3e8cdfc27346719ab63`.

Frame and contact-sheet inspection confirms that the banking shark fills most
of the display, retains one stable body, eye, gills, fins, and tail, and cycles
a visibly attached, toothless closed / half-open / open / half-open mouth. The
common textures and rare Ancestral bands remain registered to that moving
body. Across all 25 octopus variants, the former large dark eye-adjacent oval
is absent, the small actual eye stays readable, and solid, spots, stripes,
mottle, and rare Mantle rings remain attached through the sway.

The five efficient review files were uploaded to the owner-verified Google
Drive folder
[`ESP32 Phonics Picker - Device Review 2026-08-24`](https://drive.google.com/drive/folders/1xevtiQXXSPP0tzNQ_difdKQpp4dv6lIx)
under `kartiksathappan@gmail.com`; Drive readback confirmed the exact parent
folder and byte sizes:

- [mobile shark/octopus video](https://drive.google.com/file/d/1DO-3VBwJ9SR2CXZXQwKyrIwATWjPdAfx/view?usp=drivesdk),
  21,087,342 bytes;
- [all 25 reef-shark variants](https://drive.google.com/file/d/1twnWjvpO6Abk-V2aVQwymF76EGza41wv/view?usp=drivesdk),
  1,453,855 bytes, SHA-256
  `e9ed4df67801f3018a06ed35a6a89f593ffbd10a51c01c243a0735bcb26282c5`;
- [all 25 giant-octopus variants](https://drive.google.com/file/d/1Yo_yNI3jK416T_RK139mIbEMPKbNl6fY/view?usp=drivesdk),
  1,482,709 bytes, SHA-256
  `0aff2d59b6c2a8ee7a137cbd47ca262665fff695862d1da3d48ffd54288fd7f0`;
- [on-device shark chomp sequence](https://drive.google.com/file/d/1pkaX4JRbQ7DB7eAb2Ft8ufyVTSeVAYAN/view?usp=drivesdk),
  252,886 bytes, SHA-256
  `a961fd24eee9df9f3c199cc2ff435f8eb0a2cef04effe0a3128077cfcb84aebe`;
  and
- [two-species modifier overview](https://drive.google.com/file/d/1ul8hcYPbzBln_bqAkARYKWdaFpetxtkY/view?usp=drivesdk),
  624,814 bytes, SHA-256
  `3fbe1e4b8f400f0d706baf7a828484e9645ffa5ca95f32685b4fe1e02d8e96bb`.

This focused capture supersedes only the shark and octopus rows of the earlier
180-entry catalog. It does not replace the remaining hands-on touch, tilt,
double-tap/cable-removal, standby/wake, speaker-listening, or inline current
measurement gates recorded above.

## 2026-08-25 offline celebration-audio repair

This append-only entry supersedes the installed application and audio-pack
identities above. Human listening rejected both real-time and PSRAM-prepared
three-layer celebration playback as extremely scratchy even though the source
WAV payloads were intact and exhaustive integer mixing showed no clipping.
Voice and phonics through the legacy one-asset streamer remained clean, so the
failed runtime-mixing architecture was removed rather than tuned again.

The installed reward path uses 32 complete offline PCM masters: four randomized
bubble variants crossed with all eight species cues. Praise is balanced as
`(bubble variant + creature index) modulo 4`, retaining all four praise lines
for every species as its bubble varies. Every master is a byte-exact 42,240-
frame integer sum with praise at 0 ms, bubbles at 400 ms, and creature audio at
640 ms. The safety report records 32 exact composites, one runtime layer,
worst peak -4.057 dBFS, and zero clipped samples. Before the reward's first
frame is drawn, the selected 84,480-byte PCM payload is copied into fixed
internal DRAM; playback then uses the proven direct streamer with no runtime
summation and no PSRAM reads competing with the animated framebuffer.

The same user-confirmed V2 board was installed at `/dev/cu.usbmodem101`.
Esptool identified the same ESP32-S3 rev 0.2, MAC `28:84:85:8d:46:9c`, 8 MB
PSRAM, and 16 MB flash. It wrote and hash-verified all five canonical regions:
bootloader at `0x0`, partition table at `0x8000`, OTA selector at `0xe000`,
application at `0x10000`, and the audio pack at `0x610000`.

The installed application is 1,514,512 bytes with SHA-256
`c4993964bba477e06a9ddcd1d0a578655bec2b08636c867d83023461f8c89269`.
The 86-asset audio pack is 4,422,336 bytes with SHA-256
`bf7249df09e758b96c037b917afb633d796e409ecb6ad6da60cdac45d0f16be9`.
The link retained 211,856 bytes after the deterministic internal reward buffer.

A focused post-flash verifier audibly exercised a normal Glass Squid reward
(`reward_mix_b1_c4`, even bubbles, `praise_great_work`) and a rare Gulper Eel
reward (`reward_mix_b0_c7`, round bubbles, `praise_thats_it`). It proved exact
master-to-species mapping, nonrepeating consecutive bubbles, unchanged hidden
rarity counters, normal `idle -> on -> idle` audio transitions, and
`audio_write_failures=0` after both complete streams. A broader verifier was
not claimed because simultaneous live touch interaction invalidated its idle
touch-rate measurement.

The owner manually inspected celebration playback on the onboard speaker and
reported that it sounds good, closing the perceptual gate that the earlier
automated checks could not. Final serial confirmation left the board in
`standby=yes` with `audio=suspended`, `audio_power=suspended`, `mute=off`, and
`audio_write_failures=0`.
