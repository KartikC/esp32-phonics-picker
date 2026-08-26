# Development speed strategy

This is the living, project-specific plan for making DEEP SEA PHONICS TOY V2 faster to
develop without weakening its release or physical-device evidence. It records
the 2026-08-25 audit so future contributors and agents do not need the original
chat history to reconstruct the reasoning.

This document is a roadmap, not a statement that every command or mode below
already exists. The canonical supported workflow remains
[`AGENTS.md`](../AGENTS.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md). Update the
implementation-state table whenever a roadmap item ships.

For practices that apply to a different application on the same board, use
[`WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md`](WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md)
instead. In particular, DEEP SEA PHONICS TOY V2's partition layout, audio-pack offset,
asset locks, and product verification are application contracts, not general
properties of the board.

## Decision

Keep the current release path rigorous and add a separate, receipt-backed
development path.

The current repository is optimized for a reproducible release: it pins the
toolchain and board dependency, locks accepted assets and binary hashes, writes
every required flash region, performs broad serial verification, and requires
human display, touch, motion, and listening checks. Those properties should
remain.

The same work is unnecessarily expensive for each small edit. The intended
inner loop is:

```text
edit or candidate
    -> smallest relevant host test or renderer
    -> optional physical AMOLED preview
    -> one incremental development build
    -> only the changed application-owned flash region
    -> targeted device verification
    -> release lane only when the change is accepted
```

Release remains:

```text
clean build -> copied/canonicalized release artifacts -> exact manifest check
-> all five DEEP SEA PHONICS TOY V2 regions -> exhaustive device verifier -> manual gates
```

## Measured baseline

Measurements are a local 2026-08-25 snapshot, not permanent performance
claims. Preserve them as a comparison point and replace them with new measured
values after the relevant workflow changes.

| Operation | Observed time or size |
| --- | ---: |
| Host test suite | 2.8-3.9 seconds |
| Repository payload verifier | about 0.38 seconds |
| Warm toolchain setup | about 0.37 seconds |
| Source-faithful still preview | about 0.15 seconds |
| Warm/no-change firmware build | 12-15 seconds |
| Clean isolated firmware build | 31-35 seconds |
| Application image | about 1.52 MB raw |
| Audio-pack image | about 4.42 MB raw |
| Repository working directory | about 10 GB |
| Repository-local Arduino data/downloads | about 7.2 GB |

The host tests and still renderer are not the bottleneck. Repeated release
canonicalization, redundant builds, full resource transfer, exhaustive device
verification, and accepted-asset promotion dominate ordinary iteration.

## Implementation state

| Priority | Work | State | Completion evidence |
| --- | --- | --- | --- |
| P0 | Separate development and release build outputs | Proposed | Two consecutive warm development builds pass; release remains byte-reproducible |
| P0 | Source-bound build receipts and safe artifact reuse | Proposed | A stale receipt is rejected after any relevant input changes |
| P0 | Changed-region development flash planner | Proposed | Code-only changes omit the unchanged audio pack; unknown changes fail closed |
| P0 | `smoke`, focused, and `release` verifier profiles | Proposed | Each emits timed JSON; release retains all current checks |
| P1 | Candidate/watch preview through the existing `FRAME` command | Proposed | An isolated candidate appears on the physical AMOLED without promotion |
| P1 | Shared host/device RGB565 renderer and frame goldens | Proposed | Host and installed-device frame CRCs agree for scripted states |
| P1 | Declarations-only generated asset headers | Proposed | Ordinary sketch edits no longer parse asset definitions from multiple units |
| P1 | Nonblocking, versioned USB diagnostic protocol | Proposed | Partial input cannot stall rendering, touch, audio, or power handling |
| P1 | Transactional asset experiment and promotion CLI | Proposed | Candidate review never mutates accepted assets; promotion has one explicit entrypoint |
| P2 | Exact V2 board/platform layer and factory-qualification app | Proposed | DEEP SEA PHONICS TOY V2 and OceanCreatureDemo consume the same board boundary |
| P2 | Shared immutable toolchain cache and reproducible slim dependency | Proposed | Multiple projects reuse one version-keyed cache and reconstruct the same source set |
| P2 | Split and cached CI | Proposed | Fast host checks run on every change; firmware builds run only for affected or unknown paths |
| P3 | Measured ESP-IDF or Arduino-as-component vertical slice | Proposed | A written parity/performance comparison supports any migration decision |

## P0 requirements

### Keep compiler cache outputs immutable

[`scripts/build_firmware.sh`](../scripts/build_firmware.sh) currently compiles
into a persistent build directory and then calls
[`scripts/canonicalize_firmware.py`](../scripts/canonicalize_firmware.py) on the
application binary in that directory. The audit reproduced a successful cached
production build followed by `Image does not have a valid ELF header` on the
next invocation. Treat in-place post-processing of a compiler-owned cache
artifact as the primary cause until a regression test disproves it.

Required shape:

- Development builds remain incremental and do not enforce the committed
  release application hash.
- Release builds start clean, copy outputs into a release staging directory,
  and canonicalize only those copies.
- A test performs two consecutive warm builds.
- Size, partition, input, and structural validation still run in both modes.

### Bind reused artifacts to their inputs

Replace an unqualified `--no-build` path with an explicitly verified reuse
operation. A build receipt should include at least:

- Git commit plus dirty-diff digest;
- sorted digest of all relevant source, generated, configuration, and asset
  inputs;
- FQBN, toolchain, dependency, and board-profile identities;
- application and resource compatibility identifiers;
- output paths, sizes, and hashes; and
- build mode and schema version.

If a current input cannot be classified, reject reuse. The receipt and its
validation belong in deterministic code with a documented JSON schema, not in
agent instructions.

### Flash only proven-compatible changed regions during development

The canonical release continues to write bootloader, partition table, OTA
selector, application, and audio pack. A development planner may choose:

| Change class | Development write plan |
| --- | --- |
| Pure game logic, compiled renderer, or compiled visual | Application |
| Audio data, audio index, or resource schema | Application plus audio pack |
| Bootloader, partition, FQBN, toolchain, board support, or unknown | Full canonical set |
| Documentation or non-runtime public media | No flash |

An application-only plan is allowed only after a trusted full-install receipt
on the exact device, with matching bootloader, partition, and app/resource
compatibility IDs. It must still preflight ESP32-S3, 16 MB flash, the intended
port, and the user's V2-label confirmation. Any missing or conflicting evidence
falls back to the full path. A partial development install is never described
as a release deployment.

### Make verification proportional to the change

Split the current live verifier into composable profiles:

- `smoke`: board/build/resource identity, PSRAM, subsystem health, frame CRC,
  and audio readiness;
- `game`: replay, wrong answer, correct answer, reward, and round advance;
- `render`: requested layouts, letters, tilt states, mute state, and creature
  timestamps;
- `audio`: codec wake/idle, cues, selection, and mixing;
- `power`: USB mute, standby/wake, battery, and polling behavior; and
- `release`: the current exhaustive machine checks plus all manual gates.

Every profile should emit a versioned JSON receipt containing timings and the
device/build identities. A passing smoke profile proves only its stated scope.

## P1 requirements

### Preview candidates without promoting them

[`scripts/preview_on_device.py`](../scripts/preview_on_device.py) already
renders a full 368 x 448 RGB565 frame and the firmware already accepts a
USB-only `FRAME` payload. Add an explicit candidate mode that reads only an
isolated candidate, labels the state as development preview, scripts important
states, and cannot modify accepted manifests or generated runtime assets.

Then extract the production renderer behind a small fixed-allocation surface
interface so it can run in host tests. Cover the supported layouts, every
letter, tilt bounds, battery and mute states, reward timestamps, and all
creatures with golden frames. Add installed-device frame CRC or dump support so
host/device equivalence is independently checked.

Camera and human review remain required for AMOLED-specific artifacts,
perceptual color, touch alignment, animation quality, and audible quality.

### Reduce compilation amplification

The main sketch currently coordinates hardware, rendering, input, power,
diagnostics, and gameplay, and includes a generated creature header several
megabytes in size. Change generated output to a small declarations-only header
plus exactly one compiled data definition. Keep handwritten rendering logic in
ordinary source files.

Refactor by characterization rather than rewrite:

1. preserve current frame and behavior goldens;
2. reduce the sketch to composition, setup, and tick;
3. introduce a fixed-allocation `AppController` with injected clock, RNG, and
   effects;
4. extract motion, touch, power-button, and battery decoding into host-testable
   components; and
5. run native tests with sanitizers and deterministic input traces.

### Make diagnostics nonblocking and machine-readable

Replace `readStringUntil` and the long global serial timeout with a bounded,
nonblocking parser. A partial command must never block the game loop. Version
the protocol, add request IDs, separate structured responses from logs, and use
length plus CRC for binary frames.

Useful generic commands are `HELLO`, `HEALTH`, `METRICS`, `SELFTEST`, `SCENE`,
`FRAME_CRC`, `SCREENSHOT`, and deterministic `INPUT`. Report build/content/
protocol IDs, reset reason, heap and PSRAM high-water marks, render/flush
timings, I2C failures, audio underruns, and the last fault.

### Make asset promotion one explicit transaction

Experiments should record prompt, seed, provider/model, cost, source hashes,
and accepted/rejected state in a provider-independent manifest. Candidates
stay isolated and reviewable. A single promotion command should validate the
selection and transactionally update only the accepted source, generated
runtime artifact, lock/report, goldens, and public-media checklist that the
change actually requires.

Tests must be read-only. Regeneration and promotion are separate operations.

## P2 and later

- Extract an exact-board layer described in
  [`WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md`](WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md).
- Build a factory-qualification firmware before adding several development
  boards.
- Key reusable toolchain caches by operating system, architecture, CLI/core
  lock, and dependency lock; protect them with cross-process locks.
- Replace the large general vendor checkout with a deterministic, pinned
  allowlist extraction plus patch and license provenance, or a maintained fork.
- Split CI into fast host, affected firmware, and clean release jobs; cancel
  superseded branch runs.
- Evaluate ESP-IDF only through a small parity slice. Do not combine framework
  evaluation with a UI-framework or renderer rewrite.

## Iteration budgets

These are targets to measure, not claims:

| Loop | Target |
| --- | ---: |
| Pure logic to host proof | under 5 seconds |
| Candidate visual to physical AMOLED | under 5 seconds |
| Ordinary source edit to running development device | under 30 seconds |
| Smoke verification after reconnect | under 5 seconds |
| Release | Comprehensive; no duplicated build or evidence work |

Record elapsed time by phase rather than one total: environment/setup, host
tests, compile, link/image creation, erase/write/verify, reconnect, device
checks, and human evidence. Optimize the largest measured phase.

## Guardrails

- Do not weaken the canonical five-region DEEP SEA PHONICS TOY V2 release.
- Do not report compilation, host rendering, serial state, or a partial flash
  as physical release verification.
- Do not regenerate accepted assets merely to build or deploy.
- Do not auto-promote generated candidates.
- Do not guess between serial ports or board revisions.
- Do not migrate frameworks or add always-on networking merely to claim faster
  iteration.
- Put safety and deterministic behavior in normal tools and schemas so humans,
  CI, and multiple agent products all follow the same contract.

## Maintaining this plan

When an item ships, update its state and link its test or implementation. Add a
fresh before/after timing record. Remove superseded proposed commands rather
than leaving two apparent workflows. Keep the reusable board guide limited to
facts and patterns that remain valid for another application.
