# ESP32 Phonics Picker

## Product contract

This is an offline, two-choice phonics listening game for a toddler on the
Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 board (CO5300 + CST820). The physical
board reports touch at I2C `0x15`; this live probe overrides the older Amazon
listing that described the original SH8601 + FT3168 revision.

- Each round chooses one of Letterboard's 26 canonical lowercase phonics
  sounds and one different lowercase distractor.
- C and K may both be targets, but never oppose one another because Letterboard
  intentionally gives them the same `/k/` recording.
- The answer side, distractor, prompt wording, and one of six bounded card
  layouts vary independently. Layout variation is subtle and never changes hit
  area size, overlaps cards, crowds an edge, or hints at the correct answer.
- The screen contains exactly two letter cards and one fixed replay control near
  the top. There is no printed "listen", "pick one", score, or instructional
  chrome. The replay control repeats the exact current prompt and sound without
  changing the round, and restarts the current idle-nudge deadline.
- Five opening phrasings are available. Each is followed by the target Cowboy
  phonics clip; the printed screen never reveals the target sound.
- With no input, give one calm nudge at 8 seconds and a second after another 10
  seconds, then remain quiet indefinitely. A tap resets the current deadline.
- A wrong choice keeps the round in place, has no rewarding animation, and uses
  one of three calm low-energy responses.
- A correct choice gets one small 1.1-second colored card pulse and one of four
  brief praise lines, then advances. There are no scores, stars, streaks,
  applause, badges, failure screens, or ads.
- Every visible frame is composed off-screen and transferred only when complete.
  Clearing, texture drawing, glyph drawing, and animation intermediates must
  never be exposed directly on the AMOLED.
- Unused AMOLED canvas is pure black (`#000000`), with no gradient, tint, or
  decorative field. Color is reserved for the learning objects.
- Each lowercase letter has a permanent visual identity: one fixed card color
  and one fixed subtle motif. These mappings are learning anchors and must
  never be shuffled, regenerated per round, or reassigned in a later release.
- Only the cards' bounded positions vary. Position variation must not alter a
  letter's color, texture, typeface, case, or white foreground treatment.
- The onboard accelerometer slowly translates both cards together by at most 19
  horizontal and 44 vertical pixels. It never rotates them. The QMI8658 is
  mounted clockwise relative to the portrait panel, so screen motion uses
  `screen X = -sensor Y` and `screen Y = sensor X`. Motion is smoothed and
  rate-limited; the visible card positions remain their exact hit areas.
- Across all six layouts, every accelerometer position, and the full correct
  pulse, card bodies and shadows remain on-screen, never overlap one another,
  and never enter the replay control's enlarged toddler hit target. The replay
  control stays fixed while the cards move, making it a dependable target.
- Letters use a heavy rounded child-readable face with a dark halo. Texture
  contrast stays low so the glyph is always the dominant shape.
- All speech and phonics are offline authored assets. There is no microphone,
  speech recognition, account, network dependency, or runtime synthesis.

## Power behavior

- A short press-and-release of the physical PWR button toggles logical standby.
  Standby turns the AMOLED fully off, mutes the codec, disables the speaker amp,
  and pauses the current round, nudge deadline, and celebration deadline.
- Wake restores the retained complete frame before brightness, quietly primes
  the audio path, resumes the same round and remaining deadlines, and requires
  a zero-finger touch sample before accepting another choice.
- The software ignores a held PWR release at 1.5 seconds or longer and leaves
  the board's factory PMIC long-hold hard-off/cold-start behavior in control.
  BOOT/GPIO0 is not used as a power key because it is a boot strap.
- This is a polled logical standby rather than ESP deep sleep: PWR is exposed
  through XCA9554 P4, not a native RTC wake GPIO.

## Audio playback

- Playback uses the onboard ES8311 and NS4150B speaker amplifier at managed
  logical volume 100. On this board that is ES8311 `DAC_REG32 = 0xC6`
  (+3.5 dB), 10 dB above the earlier logical-80 setting. The authored -4 dBTP
  ceiling retains roughly 0.5 dB of digital headroom. This is not the legacy
  Arduino helper's unsafe linear-register interpretation.
- Codec initialization matches the current Waveshare V2 managed path, including
  a deterministic reset, 16 kHz DAC OSR `0x20`, and the complete reference and
  system-register sequence.
- Assets keep full PCM resolution and receive only a gentle 300 Hz high-pass
  and 5 kHz low-pass; there are no resonance notches or presence boosts.
  Longer speech cues use leading-silence trim only, preserving internal
  cadence, followed by two-pass -21 LUFS / -4 dBTP normalization. Short
  phonics masters retain Letterboard's relative dynamics and share one
  peak-safe -2.06 dB gain.
- The raw `ffat` pack is SHA-256 verified, then prefetched into PSRAM. Playback
  runs asynchronously so it never blocks touch or rendering, and a new
  interaction cancels stale speech.
- Real-hardware microphone captures are comparative evidence, not a substitute
  for listening on the unit. Speech recognition may catch gross failures, but
  human listening remains the final perceptual gate.
