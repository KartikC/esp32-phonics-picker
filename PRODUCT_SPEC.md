# DEEP SEA PHONICS TOY V2

This contract describes the checked-in **DEEP SEA PHONICS TOY V2**
implementation. [CURRENT_RELEASE.md](CURRENT_RELEASE.md) separately identifies
the accepted, physically installed release; newer compiled-only behavior in
this contract still requires the physical gates recorded in [AGENTS.md](AGENTS.md).
The product name is distinct from the Waveshare board's V2 hardware revision.

## Product contract

This is an offline, two-choice phonics listening game for a toddler on the
Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 board (CO5300 + CST820). The physical
board reports touch at I2C `0x15`; this live probe overrides the older Amazon
listing that described the original SH8601 + FT3168 revision.

- Each round chooses one of the 26 canonical lowercase phonics sounds and one
  different lowercase distractor.
- C and K may both be targets, but never oppose one another because the
  accepted corpus intentionally gives them the same `/k/` recording.
- The answer side, distractor, prompt wording, and one of six bounded card
  layouts vary independently. Layout variation is subtle and never changes hit
  area size, overlaps cards, crowds an edge, or hints at the correct answer.
- During an active round, the screen contains exactly two letter cards and one
  fixed replay control near the top. The control is the untouched native 64x64
  Retro Diffusion `rd_pro` Deep loop from seed `82563`, centered at `(184, 60)`
  with its 62x62 opaque silhouette inside the existing 42-pixel-radius toddler
  hit target. It is never resized or cropped. There is no printed "listen",
  "pick one", score, or instructional chrome. The replay control repeats the
  exact current prompt and sound without changing the round, and restarts the
  current idle-nudge deadline.
- The only parent-facing status mark is a centered row of three-pixel-radius
  dots at the extreme top edge: three dim green dots mean high/full (60-100%),
  two dim yellow dots mean medium (25-59%), and one dim red dot means low
  (0-24%). It has no text, animation, touch target, or gameplay meaning and is
  sampled only every 30 seconds.
- Five opening phrasings are available. Each is followed by the target Cowboy
  phonics clip; the printed screen never reveals the target sound.
- With no input, give one calm nudge at 8 seconds and a second after another 10
  seconds, then remain quiet indefinitely. A tap resets the current deadline.
- One awake play period lasts exactly ten accumulated minutes (`600000 ms`).
  Ordinary rounds, idle time, wrong-answer feedback, and correct-answer rewards
  all count. Physical standby and USB diagnostic previews pause the allowance.
  If the limit lands during an unanswered round, input locks immediately. If an
  answer transition is already underway and the board remains awake, its
  complete neutral or reward sequence and black beat finish first, but its next
  spoken round is held until after the break. PWR standby retains the visual
  transition deadline but intentionally cancels in-flight PCM as part of the
  fail-safe audio power-down; wake does not replay a partially heard cue.
- The play limit replaces the choice UI with a full-screen rest timer beginning
  at `30:00`. It uses the untouched native 128x128 Retro Diffusion `rd_pro`
  Shell-inlay tideglass from seed `82802`, centered at x=184 with its top at
  y=54, plus one deterministic firmware-rendered `MM:SS` countdown, an elapsed
  progress track, the small word `rest`, and the normal tiny battery dots on a
  physically black AMOLED background. No generated text is baked into the
  artwork. Remaining time is derived from elapsed milliseconds and rounded up
  to the displayed second; a changed second or battery-state refresh redraws
  the complete framebuffer.
- A rest lasts thirty elapsed minutes (`1800000 ms`). During it, touch, tilt,
  replay, nudges, phonics prompts, rewards, and gameplay diagnostics cannot
  resume or cover the mandatory timer. Short-PWR standby turns the panel off
  but the rest deadline continues. Wake shows the correct remaining time, or
  speaks the already-selected unseen challenge (otherwise a newly selected
  challenge) if rest completed while asleep. The next ten-minute allowance
  begins only after that fresh challenge is installed. A PMIC hard-off, reset,
  or cold boot starts a fresh play allowance; this implementation does not
  claim a power-loss-resistant parental lockout.
- A wrong choice freezes the answered round for at least 1100 ms while the
  neutral 830 ms "No, no." cue plays. Card, replay, motion, and diagnostic
  input stay locked. The compositor then shows one complete 120 ms black beat
  before atomically drawing and speaking a new challenge; a busy loop may
  delay that beat but can never skip it. There is no rewarding animation and
  no second try on the answered challenge.
- A correct choice gets one of four brief praise lines and a 3.28-second reward
  transition: the correct card confirms for 400 ms, water rises from 400-640
  ms, and one large animated creature is visible from 640-3160 ms. The
  full-water hold lasts through 2880 ms, water recedes from 2880-3160 ms, and a
  fully black 120 ms beat precedes the next round at 3280 ms. The device-
  rounded 2520 ms creature window is 14.5% longer than the previous 2200 ms
  window: the exact 15% target is 2530 ms and the renderer advances on a 40 ms
  transition cadence. Choice and replay input stay locked throughout.
- Correct-answer audio follows those same visual boundaries. Praise begins at
  0 ms, one of four independently randomized bubble beds begins at 400 ms,
  and the selected species' cue begins at 640 ms. The bubble therefore leads
  the creature by 240 ms and the two effects overlap through the middle of the
  reward. Audio ends by 2680 ms, preserving a quiet 600 ms tail before the
  next round. The shark uses the reviewed rounded pressure pulse and disturbed
  bubbles that follows its chomp; the other seven cues remain species-specific.
  Immediate bubble repeats are excluded.
- While the creature is visible from 640-3160 ms, its animal name is shown on
  one tiny, centered line at the bottom. It remains adult-legible and
  unobtrusive, is not a score or rarity label, and is absent during the water
  rise, terminal black beat, and choice round.
- Every correct answer earns one of exactly eight creatures: moon jelly, reef
  shark, giant octopus, seahorse, glass squid, anglerfish, sea angel, or gulper
  eel (displayed as "Deep-sea eel"). Base species selection uses 80:30:16 weights
  for three tiers: basic contains moon jelly, seahorse, and glass squid; medium
  contains giant octopus and sea angel; rare contains reef shark, anglerfish,
  and gulper eel. The reward selector owns a separate random stream, never
  changes the phonics round sequence, and avoids immediate species and palette
  repeats.
- Base species tier is independent of the authored rare-treatment roll: a
  rare-tier species can receive a normal treatment, and a basic-tier species
  can receive its authored rare treatment. Most normal rewards vary one of five
  approved non-purple color ramps; translucent glass squid and sea angel are
  limited to Tide slate, Kelp green, and Moon pale. Normal rewards also vary a
  solid/spotted/striped/mottled pattern-safe body treatment. Every creature
  keeps its four-frame base animation under both normal and rare modifications,
  with protected anatomy unchanged. The anglerfish lure follows a warm
  dim/medium/bright/medium pulse;
  the screen-filling reef shark uses the selected `82412` three-quarter banking
  pose and a reviewed Retro Diffusion sprite-sheet bite: exact closed source,
  half-open, clearly open, and the identical half-open recovery. Its body, eye,
  and gills stay registered while a synchronized short lunge adds activity.
- Authored rare-treatment rewards use the selected creature's species-specific
  treatment and, where that species permits it, restrained sparkles. Sea angel
  explicitly keeps its clean translucent silhouette with no generic sparkles.
  Rare treatments do not add a score or gameplay advantage. In a clean run,
  correct answers 1-3 have 1/43 hidden odds, answers 4-6 have 1/21 odds,
  answer 7 has 1/11 odds, and answer 8 is guaranteed rare. A separate
  12-correct pity counter survives mistakes, so errors cannot make a rare
  unreachable. Together, the rounded hazards and guarantees raise effective
  rare-treatment incidence by 24.26% in a clean run and 16.45% when every
  correct answer is separated by a mistake. A wrong answer resets only clean
  progress and then advances to a new challenge. Neither counter nor rarity is
  printed on the child-facing screen.
- There are no visible scores, stars, streak counters, applause, badges,
  failure screens, or ads.
- Every visible frame is composed off-screen and transferred only when complete.
  Clearing, texture drawing, glyph drawing, and animation intermediates must
  never be exposed directly on the AMOLED.
- Unused AMOLED canvas during the choice round is pure black (`#000000`), with
  no gradient, tint, or decorative field. The animated blue-green water exists
  only inside the correct-answer reward transition. Its seabed remains quiet
  and contains no stationary decorative circles.
- Each lowercase letter has a permanent visual identity: one fixed stonewashed
  card color and one fixed subtle motif. The 26 unique RGB565 colors stay
  inside a weathered clay, lichen, sage, sea-glass, slate, heather, and ochre
  family. These mappings are learning anchors and must never be shuffled,
  regenerated per round, or reassigned in a later release.
- Every card uses the exact selected Retro Diffusion `rd_pro` seed `82521`
  carved tide-stone silhouette. Its irregular chips, cracks, asymmetrical
  bevel, and eight semantic source regions are retained in one compact packed
  map. Every visible region is a narrow lightness step derived from the
  letter's stonewashed base color. No fixed cyan glint or navy crack color may
  appear: the source geometry remains, but its texture is tone-on-tone so all
  26 cards read as the same subtle weathered material without green specks or
  blue line artifacts.
- Each letter-derived motif keeps 13 permanent anchors and one of four motif
  families. It is rendered as a shallow light/dark incision and clipped to the
  source stone's broad central plane, never painted over the bevel or cracks.
- Card shadows use the fixed near-black blue-grey source target `#040B11`,
  quantized to RGB565 `0x0042`. They must not use the former `0x0204`, which
  decodes as a visibly green shadow along the stone's bottom-right silhouette.
- Only the cards' bounded positions vary. Position variation must not alter a
  letter's color, texture, typeface, case, or white foreground treatment.
- The onboard accelerometer translates both cards toward the same tilt target
  by at most 19 horizontal and 44 vertical pixels. It never rotates them. Each
  card has a subtly different per-round easing rate (10.5-12.8% per sample), so
  one gently leads or trails the other. Relative horizontal separation is
  clamped from -2 to +6 pixels and vertical separation to 8 pixels, preserving
  the safe visual pair while making the motion feel less mechanical. The QMI8658 is
  mounted clockwise relative to the portrait panel, so screen motion uses
  `screen X = -sensor Y` and `screen Y = sensor X`. Motion is smoothed and
  rate-limited; the visible card positions remain their exact hit areas.
- Across all six layouts, every accelerometer position, and the full correct
  pulse, card bodies and shadows remain on-screen, never overlap one another,
  and never enter the replay control's enlarged toddler hit target. The replay
  control stays fixed while the cards move, making it a dependable target.
- Letters use Atkinson Hyperlegible Next ExtraBold 800 at a nominal 112 px,
  one-bit rasterized for the device and mathematically centered from each
  visible glyph's bounds. A fixed deep-slate halo and white foreground preserve
  separation. All 26 lowercase glyphs plus the two-pixel halo fit inside the
  138-by-158 card; texture contrast stays low so the glyph is dominant.
- All speech and phonics are offline authored assets. There is no microphone,
  speech recognition, account, network dependency, or runtime synthesis.

## Power behavior

- A short press-and-release of the physical PWR button toggles standby.
  Standby turns the AMOLED fully off, powers down the codec and I2S path,
  disables the speaker amp and accelerometer, and pauses the current round,
  nudge deadline, and celebration deadline.
- Wake restores the retained complete frame before brightness, quietly primes
  the audio path, resumes the same round and remaining deadlines, and requires
  a zero-finger touch sample before accepting another choice. Audio interrupted
  by standby is not resumed mid-asset or replayed; the next newly scheduled cue
  uses the normally restored path.
- The software ignores a held PWR release at 1.5 seconds or longer and leaves
  the board's factory PMIC long-hold hard-off/cold-start behavior in control.
  Hold PWR for 6 seconds to hard-off; from hard-off, click PWR once to start.
  USB charging remains available while the board is hard-off.
  BOOT/GPIO0 is not used as a power key because it is a boot strap.
- On battery or charge-only USB, standby uses 50 ms timer-woken ESP light-sleep
  intervals and polls PWR between them. PWR is exposed through XCA9554 P4, not
  a native ESP wake GPIO, so an indefinite PWR-woken sleep is not possible
  without a hardware change. With a real USB data host attached, standby keeps
  the processor awake and polls normally because native USB Serial/JTAG is not
  guaranteed to survive light sleep; the display, IMU, codec, I2S, and amplifier
  remain powered down. See `docs/POWER_AUDIT.md` for the schematic constraint,
  research basis, measurement plan, and awake-mode audit.
- While awake, the PWR expander is sampled every 20 ms. Idle touch reads are
  gated by the CST820 interrupt, with the original 8 ms cadence retained from
  contact through release and a 64 ms missed-edge safety poll. If interrupt
  setup fails, firmware deliberately returns to continuous polling rather than
  risking an unresponsive screen. These optimizations must not change touch or
  PWR semantics.

## Audio playback

- A maintenance mute exists only while a real USB data host is attached, as
  reported by USB CDC host traffic rather than charger voltage. Double-tapping
  anywhere in the replay control's complete 42-pixel-radius hit target within
  500 ms toggles mute. A lone tap becomes replay after that window. With no
  data host, every replay tap is immediate and the gesture cannot enter mute.
- While muted, a two-pixel warm-red diagonal slash crosses the otherwise
  unchanged Deep loop control. That mark is never shown without the data host.
  Mute is not persisted and clears after 1.8 seconds of sustained data
  disconnect. Standby and maintenance mute share the same fail-safe codec mute
  and speaker-amplifier gate; waking never overrides an active maintenance
  mute.

- Playback uses the onboard ES8311 and NS4150B speaker amplifier at managed
  logical volume 90. On this board that is ES8311 `DAC_REG32 = 0xBC`, 5 dB
  below the former logical-100 setting. The reduction supplies approximately
  5.5 dB above the authored -4 dBTP speech peaks for the DAC and tiny speaker,
  while preserving all authored category relationships. This is not the
  legacy Arduino helper's unsafe linear-register interpretation.
- Playback allocates only the I2S transmit path. After the final authored 40 ms
  silence plus a 750 ms idle guard, firmware mutes and powers down the codec,
  gates the speaker amplifier, and disables I2S transmit. A later cue restores
  the path while muted, preloads silence, enables the amplifier, waits 10 ms,
  and unmutes before queuing its first PCM frame. This idle power transition is
  transparent to later replay, wrong-answer, praise, next-round, and
  maintenance-mute behavior; explicit standby instead cancels any in-flight
  PCM and does not resume it mid-asset. After unmuting, every cold wake feeds
  120 ms of digital silence through I2S before the first authored PCM frame so
  the ES8311 and speaker amplifier cannot swallow an opening consonant.
- Codec initialization matches the current Waveshare V2 managed path, including
  a deterministic reset, 16 kHz DAC OSR `0x20`, and the complete reference and
  system-register sequence.
- Assets keep full PCM resolution and receive only a gentle 300 Hz high-pass
  and 5 kHz low-pass; there are no resonance notches or presence boosts.
  Longer speech cues use leading-silence trim only, preserving internal
  cadence, followed by two-pass -21 LUFS / -4 dBTP normalization. Short
  phonics masters retain their reviewed relative dynamics. All 26 device
  phonics clips receive one shared 1.32x amplitude boost (+2.411 dB) over their
  originally accepted levels, with a measured peak sample of 27,261 and no
  clipping; speech, praise, bubble beds, and creature effects are unchanged.
- Reward effects use the same speaker filter and PCM path. Bubble beds are
  authored around -28 LUFS with a -9 dBTP ceiling; every creature master gets
  one shared +1.5 dB lift, with sparse transient cues left uncompressed to
  preserve their character. The accepted speech and phonics masters are not
  renormalized. All 32 deployed bubble-by-creature celebration masters must be
  byte-exact offline integer sums with zero clipped samples before a pack is
  accepted. Praise is balanced as `(bubble + creature) modulo 4`, so every
  species still reaches all four phrases while bubble randomness remains in
  its independent, no-immediate-repeat domain.
- The raw `ffat` pack is SHA-256 verified, then prefetched into PSRAM. Playback
  runs asynchronously so it never blocks touch or rendering, and a new
  interaction cancels stale speech. Every three-part celebration is authored
  offline as one complete 2.64-second PCM asset with praise at 0 ms, bubbles at
  400 ms, and the creature gesture at 640 ms. Before reward drawing starts,
  firmware copies that single selected asset into a fixed 84,480-byte internal-
  DRAM buffer. It then uses the same contiguous one-asset 16-bit streamer as
  clean speech and phonics: no runtime summation and no PSRAM access competes
  with the animated framebuffer during celebration playback.
- Real-hardware microphone captures are comparative evidence, not a substitute
  for listening on the unit. Speech recognition may catch gross failures, but
  human listening remains the final perceptual gate.
