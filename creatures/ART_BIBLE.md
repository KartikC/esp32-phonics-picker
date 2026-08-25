# Pocket Reef creature art bible

## Production target

- Hardware: Waveshare ESP32-S3-Touch-AMOLED-1.8 V2, 368 x 448 portrait AMOLED.
- Source candidates: 128 x 128 RGBA pixel art.
- Runtime logical sprites and four-frame motion:

  | Species | Tier / weight | Logical / scale | Display footprint | Motion highlight |
  |---|---:|---:|---:|---|
  | Moon jelly | Basic / 8 | 88 x 120 / 3x | 264 x 360 | Bell pulse and connected-tentacle sway |
  | Reef shark | Rare / 1 | 120 x 124 / 3x | 360 x 372 | Reviewed sprite-sheet chomp and short lunge |
  | Giant octopus | Medium / 3 | 96 x 112 / 3x | 288 x 336 | Mantle bob and connected-arm sway |
  | Seahorse | Basic / 8 | 80 x 112 / 3x | 240 x 336 | Gentle body bob and lower-tail sway |
  | Glass squid | Basic / 8 | 80 x 112 / 3x | 240 x 336 | Mantle contraction and attached arm-tip sway |
  | Anglerfish | Rare / 1 | 112 x 72 / 3x | 336 x 216 | Calm hover, tail paddle, and warm lure pulse |
  | Sea angel | Medium / 3 | 88 x 96 / 4x | 352 x 384 | Symmetrical wingbeat and small body lift |
  | Deep-sea eel | Rare / 1 | 112 x 88 / 3x | 336 x 264 | Traveling body bend that fades before the head |

  The production squid is the selected **glass squid**, not the preview-only
  vampire-squid candidate.
- One creature is shown at a time and owns most of the display. Its small name
  is centered at the bottom of the reward scene.
- Runtime format: four-bit indexed color with index zero reserved for transparency.
- Animation: four reviewed frames. Most species derive deterministic motion
  from one approved anchor; the reef shark uses a source-conditioned external
  sprite sheet whose body is restored exactly outside a bounded mouth patch.

The small screen rewards the same qualities that make good side-view diving games
readable: strong silhouettes, quiet interiors, bright accents against deep water,
and motion that can be understood in a few frames. This is an original visual
system. Do not reproduce another game's characters, sprite sheets, compositions,
logos, or exact palette.

## Shape language

- Jellyfish: broad luminous bell, narrow waist, a few connected tentacle groups,
  and a centered vertical silhouette. It must read on the 88 x 120 logical grid
  without depending on tiny highlights.
- Reef shark: the selected seed `82412` is a strongly foreshortened
  three-quarter banking turn. Its lower-right head and near pectoral fin fill
  the foreground while the body curls in a broad C to the upper-left forked
  tail. Preserve that exact pose; do not flatten it back into a profile.
- Giant octopus: broad mantle and eight connected arms in one silhouette; eye,
  mouth, suckers, arm roots, and tips remain protected during variation.
- Seahorse: upright torso, readable snout and crest, small fin, and one clearly
  curled connected tail.
- Glass squid: pale tapered mantle, two readable eyes, visible broad internal
  forms, and short connected arms. Do not substitute the vampire-squid concept.
- Anglerfish: compact heavy head, closed toothless mouth, tapered tail, and one
  connected forehead lure with a warm dim/medium/bright/medium pulse.
- Sea angel: vertically centered tapered body, paired head tentacles, and two
  broad symmetrical swimming lobes. Keep the internal glow attached.
- Deep-sea eel: enlarged calm pouch head, long continuous curved body, and a
  narrow attached tail tip; no exposed teeth or detached glow.
- Keep eyes and facial marks tiny. The animal silhouette, not a cartoon face, is
  the primary read.
- One animal per transparent asset. No bubbles, prey, ground, scenery, label,
  border, shadow, or detached sparkle pixels.
- Prefer clusters at least two logical pixels thick. Avoid single-pixel noise,
  fine stippling, thin interior lines, and details that disappear at arm's length.

## Shared 15-color palette

Index zero is transparent. The remaining roles are fixed so every approved
candidate is converted into a coherent device pack.

| Role | Hex |
|---|---|
| Ink | `#071522` |
| Deep blue | `#0B2A3C` |
| Ocean blue | `#124A60` |
| Slate | `#35677A` |
| Shark blue | `#5F8FA0` |
| Silver | `#91B7BE` |
| Foam | `#D8EEF0` |
| White glint | `#F7FFFF` |
| Cyan | `#27D3D0` |
| Electric blue | `#2588D8` |
| Lavender | `#7667C5` |
| Jelly violet | `#B45CC7` |
| Coral | `#E06C8C` |
| Warm glow | `#F3B56B` |
| Soft yellow | `#F4E39B` |

## Generation gates

1. Correct species and a single readable silhouette at target display size.
2. Approved pose and facing. Most animals are side-readable; the selected reef
   shark is explicitly the reviewed three-quarter banking C pose.
3. Transparent background with no scenery or detached debris.
4. Complete animal inside the canvas with at least four source pixels of safety.
5. No text, logo, watermark, frame, contact sheet, or multiple view.
6. The candidate remains coherent after conversion to the shared palette.

Raw external generations are review candidates, never runtime assets. A named
selection, deterministic conversion, device-scale preview, hashes, and a passing
production audit are required before a sprite enters firmware.

## Runtime variation contract

Base-species rarity is a weighted selection axis: basic species use weight `8`,
medium species `3`, and rare species `1`. Immediate species repeats are
removed. This is independent of the hidden authored-treatment roll: every one
of the eight species can appear with a normal solid/spotted/striped/mottled
treatment or with its own rare motif, while retaining the same four-frame base
animation and protected anatomy.

Automatic play never selects Plum deep. Most species may use palette indices
`0, 1, 2, 4, 5`; translucent glass squid and sea angel are deliberately limited
to `0, 1, 5` (Tide slate, Kelp green, and Moon pale). Palette selection avoids
an immediate repeat whenever another allowed ramp exists.

The authored rare motifs are Celestial bell, Ancestral bands, Mantle rings,
Royal diamonds, Prismatic panes, Abyssal constellation, Halo wings, and Ghost
current in manifest order. Their selection is a visual reward variation, not a
different base-species tier or gameplay advantage.
