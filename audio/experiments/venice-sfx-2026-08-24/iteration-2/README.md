# Venice SFX iteration two

This audition follows the first-pass selection of ElevenLabs Sound Effects V2.
It does two things:

1. makes three close siblings of the selected generic bubble sound;
2. replaces the shark's generic glide with water shaped by its animated chomp.

Nothing in this folder is part of the canonical audio pack or installed
firmware.

## Bubble reel

`bubble-variants-reel.wav` has four two-second clips separated by 0.5 seconds:

1. original selected bubbles — the reference from iteration one;
2. even three — evenly spaced rising bubbles and a plip;
3. larger last — two small bubbles, a larger hollow bubble, then a plip;
4. pinhead cascade — four small bubbles and a lower final plup.

The references and variants receive the same mono 16 kHz device processing.

## Shark reel

`shark-chomp-variants-reel.wav` has four two-second clips separated by 0.5
seconds:

1. original glide — the reference from iteration one;
2. pressure pulse — jaw closure represented as displaced-water pressure,
   ripple, and two bubbles;
3. glide plus chomp — a short approach followed by one compact water whoomp;
4. suction wake — inward water motion, closure pulse, folded wake, and
   microbubbles.

These are intentionally hydrodynamic rather than literal mouth effects. The
prompts prohibit teeth, crunching, roaring, attack sounds, and large splashes.
The `glide plus chomp` output is much quieter in integrated loudness because a
few isolated transients reach the peak ceiling; the file is not missing or
damaged.

## Files and cost

- `generation-requests.json` records exact prompts and queue IDs.
- `raw/` preserves untouched provider responses.
- `device-preview/` contains mono 16 kHz PCM previews plus the two references.
- `analysis/` contains individual plots and two labeled spectrogram sheets.
- `results.json` records hashes, formats, measured levels, and reel order.

The six successful generations were each quoted at $0.01, for an iteration-two
quoted total of **$0.06 / 0.06 DIEM**. All six requests were marked complete at
the provider after local download.
