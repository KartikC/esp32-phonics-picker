# DEEP SEA PHONICS TOY V2

- **Accepted:** 2026-08-25
- **Git tag:** `v2.0.0`
- **Hardware:** Waveshare ESP32-S3-Touch-AMOLED-1.8 V2 (CO5300 + CST820)

DEEP SEA PHONICS TOY V2 is the current child-tested, accepted product release. The
product release name is separate from the hardware revision, which also uses
the label V2.

## Installed identities

- Application: 1,522,544 bytes, SHA-256
  `c06fb68793e8bd11224d716440faf29ae990d610f2448e5bc4000cfa60240687`
- Audio pack: 4,473,882 bytes, SHA-256
  `262858b9569618ca7bb901ba27fc0fd9034eb2f9e11a82176cda8ace7db19ba0`

The canonical host and firmware suites passed, all five flash regions were
written and hash-verified, and the complete serial device verifier passed with
zero audio write failures. Hands-on family use then found the installed
experience solid and a meaningful improvement over the prior version used by
the child.

## Newer connected-device validation

On 2026-08-28, the supported V2 board was updated to source through commit
`fdd8da4` for the ten-minute play/30-minute rest timer, longer creature reward,
higher rare-species and rare-treatment incidence, and locked wrong-answer
advance to a different challenge. The application is 1,535,408 bytes with
SHA-256
`019fcb5243c5c0fa7cef535bcc7d540dbb016de4616a5136e1ceff4fe11af93e`;
the accepted audio-pack identity above is unchanged. All five flash regions
were hash-verified and the complete serial verifier passed with zero audio
write failures.

This is a newer installed validation build, not a replacement acceptance
claim. The full ten-minute/30-minute timer cycle and the hands-on display,
touch, tilt, maintenance double-tap/disconnect, PWR, timing, and listening gates
remain outstanding, so `v2.0.0` remains the current child-tested accepted
release.
