# Venice reward-sound audition — 2026-08-24

This folder is an isolated audition. None of these files is part of the
canonical phonics audio pack, firmware index, build manifest, or installed
device state.

## Recommendation

Keep the two-card scene silent on taps. It already answers every tap with
speech or a reward, and the current audio engine intentionally plays one
sequence rather than mixing layers. A generic tap would make the learning
scene busier without adding meaning.

For a correct answer, the promising arrangement is:

1. keep the existing 0.494–0.745 second praise line;
2. follow it with one quiet species cue;
3. let the cue end before the 2.96 second reward transition completes.

A 2.0 second cue following the longest praise and the existing 40 ms sequence
gap ends at about 2.785 seconds (about 2.825 seconds including the engine's
final gap). It therefore fits the visual reward without speaking over the next
round. This is a timing proposal only; it has not been put into firmware.

## Current Venice model research

The authenticated `GET /api/v1/models?type=music` response returned 14 models.
The unmodified response is saved as `authenticated-model-catalog.json`.

Four entries were relevant to short game effects:

| Model | Model constraint and authenticated price | Result |
| --- | --- | --- |
| ElevenLabs Sound Effects V2 | 1–22 seconds, loop-capable, $0.0023/second | Selected. The common prompt arrived at -23.7 LUFS / -14.0 dBFS true peak and showed rounded repeated bubble gestures. |
| MMAudio V2 | 1–30 seconds, $0.00092/second | Rejected for this direction. The common prompt arrived at -18.0 LUFS and +1.5 dBFS true peak, with repeated broadband impacts. |
| Sonilo V1.1 Sound Effects | 1–180 seconds, $0.00207/second | Rejected for this direction. The common prompt arrived at -9.1 LUFS / -0.9 dBFS and formed a dense continuous bed. |
| Stable Audio 2.5 | 5–190 seconds, fixed $0.19/generation | Not generated. Its five-second minimum and fixed price are a poor match for a 2.2-second creature window. |

Venice documents audio generation as an asynchronous queue/retrieve workflow,
and recommends quoting before queueing and completing a request after media is
downloaded. All 11 successful requests in this audition were marked complete
after the local files were hash-checked.

## Sound family

The eight sketches share a quiet, dry, late-1990s handheld-game vocabulary:
rounded water gestures, a restricted 300 Hz–5 kHz device band, no music, no
voice, no large splash, no reverb tail, and no invented animal roars.

The creature identity comes from motion-like foley:

| Reel order | Creature | Gesture |
| ---: | --- | --- |
| 1 | Moon Jelly | gelatinous bloops and rising bubbles |
| 2 | Reef Shark | smooth water glide and one muted bubble |
| 3 | Giant Octopus | padded suction pops and a low bubble |
| 4 | Seahorse | tiny clicks and pinhead bubbles |
| 5 | Glass Squid | hollow water droplet and airy bubbles |
| 6 | Anglerfish | low bubble, muted lure ping, small bubble |
| 7 | Sea Angel | soft underwater flutter and bright bubbles |
| 8 | Gulper Eel | hollow bubble gulp and folded water motion |

Exact submitted prompts and queue IDs are in `generation-requests.json`.

## Audition files

- `species-audition-reel.wav` contains all eight device previews in the table
  order, separated by 0.5 seconds of silence.
- `model-comparison-reel.wav` contains the same shared-bubble prompt in this
  order: ElevenLabs, MMAudio, Sonilo, with 0.75 second gaps.
- `device-preview/` contains individual mono 16 kHz PCM WAV files.
- `raw/` preserves the untouched Venice responses.
- `analysis/species-device-spectrogram-contact-sheet.jpg` shows the eight
  processed frequency/time signatures.
- `results.json` records hashes, formats, duration, loudness, true peak, and
  reel order.

Device previews use two-pass loudness processing with a -28 LUFS target and a
-9 dBTP ceiling, then mono 16 kHz signed 16-bit PCM. The anglerfish and
seahorse cues remain quieter in integrated loudness because their isolated
transients hit the peak ceiling first; they were not compressed merely to make
the meter match.

Human listening on the actual Waveshare V2 speaker remains the acceptance
gate. These files have not been flashed or heard on the board.

## Cost accounting

Each request was quoted before generation. Venice rounded every two-second
quote to $0.01, so the 11 successful requests have a quoted total of **$0.11
(0.11 DIEM)**. The per-second catalog arithmetic would be $0.04738 before that
request-level quote rounding. The current API key can generate audio but gets
`401 Admin API key required` from both billing balance and usage-history
endpoints, so a separate settled ledger total could not be read. Queue response
headers did show a 0.04 DIEM balance drop after a four-clip batch, consistent
with the rounded quotes.

## If the audition is approved

The next implementation should add only the accepted cues to the generated
audio pack and index, map cue IDs to the selected reward species, and extend
the existing praise call to a two-asset sequence. That change would also need
the product spec, pack/build manifests, host tests, full firmware test, a
five-region flash, automated device verification, and human listening on the
V2 board. No such production change is part of this experiment.
