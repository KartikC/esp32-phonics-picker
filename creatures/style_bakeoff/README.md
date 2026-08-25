# Choose a water-creature style

Open `generated/style_comparison.png` and choose one column:

1. **Luminous modern** — cool, polished, volumetric, and detailed.
2. **Evolutionary 16-bit** — chunky outlines, flat bands, and maximum classic
   console readability.
3. **Reef hybrid** — warm biological accents with a strong 16-bit silhouette.
4. **AMOLED minimal** — near-black negative space and the fewest details.

Every column contains the same four subjects at their intended ESP32 logical
resolution and 3x display scale. These are comparison candidates, not production
firmware assets. After a style is chosen, generate multiple fixed-seed candidates
within that one direction, select per animal, and pass them through the existing
production pack audit.

Regenerate the matrix with the authoring-only API keys available:

```sh
python3 scripts/generate_creature_style_bakeoff.py
```

Rebuild only the comparison sheets from existing candidates:

```sh
python3 scripts/generate_creature_style_bakeoff.py --sheet-only
```
