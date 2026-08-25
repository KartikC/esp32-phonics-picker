#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_XCA9554.h>
#include "Arduino_GFX_Library.h"
#include "HWCDC.h"
#include "pin_config.h"

#include "../CreatureAssets/GeneratedCreatureVariations.h"

using namespace creature_variations;

HWCDC& USBSerial = HWCDCSerial;
Adafruit_XCA9554 expander;

Arduino_DataBus* displayBus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_CO5300* panel = new Arduino_CO5300(
    displayBus, GFX_NOT_DEFINED, 0, LCD_WIDTH, LCD_HEIGHT, 16, 0, 0, 0);
Arduino_Canvas* gfx = new Arduino_Canvas(LCD_WIDTH, LCD_HEIGHT, panel);

constexpr uint8_t kDisplayBrightness = 178;
constexpr uint32_t kFrameIntervalMs = 100;
constexpr uint32_t kAutoAdvanceIntervalMs = 2600;
uint32_t lastFrameAtMs = 0;
uint32_t lastAutoAdvanceAtMs = 0;
uint8_t creatureIndex = 0;
uint8_t paletteIndex = 0;
uint8_t frozenFrame = 0;
PatternStyle patternStyle = PatternStyle::kSolid;
uint32_t patternSeed = 0xC0A57EEDu;
RenderMode renderMode = RenderMode::kColor;
bool autoAdvance = true;
bool animationFrozen = false;
bool rareEnabled = false;

uint16_t color565(uint8_t red, uint8_t green, uint8_t blue) {
  return static_cast<uint16_t>(((red & 0xF8) << 8) |
                               ((green & 0xFC) << 3) |
                               (blue >> 3));
}

void drawWater(uint32_t now) {
  uint16_t* framebuffer = gfx->getFramebuffer();
  for (int16_t y = 0; y < LCD_HEIGHT; ++y) {
    const uint8_t red = 5 + (2 * y) / LCD_HEIGHT;
    const uint8_t green = 39 - (20 * y) / LCD_HEIGHT;
    const uint8_t blue = 58 - (24 * y) / LCD_HEIGHT;
    const uint16_t color = color565(red, green, blue);
    uint16_t* row = framebuffer + static_cast<uint32_t>(y) * LCD_WIDTH;
    for (int16_t x = 0; x < LCD_WIDTH; ++x) row[x] = color;
  }

  // The background stays code-native and cheap; generated pixels are reserved
  // for reviewed animals whose silhouette benefits from authored sprite art.
  gfx->fillTriangle(0, 407, 83, 389, 168, LCD_HEIGHT, 0x08C6);
  gfx->fillTriangle(112, LCD_HEIGHT, 237, 393, 367, LCD_HEIGHT, 0x08C6);

  constexpr int16_t bubbleX[] = {36, 49, 319, 330, 286};
  constexpr int16_t bubbleBaseY[] = {112, 88, 182, 151, 274};
  for (uint8_t index = 0; index < 5; ++index) {
    const int16_t travel = static_cast<int16_t>((now / (36 + index * 7)) % 48);
    const int16_t y = bubbleBaseY[index] - travel;
    gfx->drawCircle(bubbleX[index], y, index % 2 ? 2 : 3, 0x2E99);
  }
}

const char* renderModeName() {
  switch (renderMode) {
    case RenderMode::kColor: return "COLOR";
    case RenderMode::kProtectionMask: return "SAFE MASK";
    case RenderMode::kTextureProbe: return "TEST PROBE";
  }
  return "UNKNOWN";
}

const char* patternStyleName(PatternStyle pattern) {
  switch (pattern) {
    case PatternStyle::kSolid: return "SOLID";
    case PatternStyle::kSpots: return "SPOTS";
    case PatternStyle::kStripes: return "STRIPES";
    case PatternStyle::kMottle: return "MOTTLE";
  }
  return "UNKNOWN";
}

void advancePatternSeed() {
  // Deterministic sequence so a treatment can be reproduced from serial logs.
  patternSeed = patternSeed * 1664525u + 1013904223u;
}

void printStatus() {
  const CreatureSprite& sprite = *kCreatures[creatureIndex];
  USBSerial.printf("[state] creature=%u:%s palette=%u:%s mode=%s pattern=%u:%s seed=0x%08lx rare=%u:%s auto=%u frozen=%u\n",
                   creatureIndex, sprite.id, paletteIndex, kPaletteNames[paletteIndex],
                   renderModeName(), static_cast<uint8_t>(patternStyle),
                   patternStyleName(patternStyle), static_cast<unsigned long>(patternSeed),
                   rareEnabled, sprite.rareTreatmentLabel, autoAdvance, animationFrozen);
}

void printHelp() {
  USBSerial.println("[controls] c=next creature, p=next palette, t=next pattern, r=toggle rare, s=next deterministic seed");
  USBSerial.println("[controls] d=color/mask/probe, h=freeze animation, a=toggle auto, v=full treatment self-test, ?=help/status");
}

void runProtectionSelfTest() {
  constexpr uint32_t kSelfTestSeed = 0xC0A57EEDu;
  uint32_t safePixels = 0;
  uint32_t protectedPixels = 0;
  uint32_t exercisedPixels = 0;
  uint32_t invalidSafePixels = 0;
  uint32_t protectedChanges = 0;
  uint32_t patternExercised[kPatternCount] = {};
  uint32_t patternProtectedChanges[kPatternCount] = {};
  uint32_t rareExercised = 0;
  uint32_t rareProtectedChanges = 0;
  uint16_t missingPatternFrames = 0;
  uint16_t missingRareFrames = 0;
  for (uint8_t creature = 0; creature < kCreatureCount; ++creature) {
    const CreatureSprite& sprite = *kCreatures[creature];
    for (uint8_t frame = 0; frame < kFrameCount; ++frame) {
      uint32_t framePatternExercised[kPatternCount] = {};
      uint32_t frameRareExercised = 0;
      const uint8_t* semantic = reinterpret_cast<const uint8_t*>(
          pgm_read_ptr(&sprite.semanticFrames[frame]));
      const uint8_t* safeMask = reinterpret_cast<const uint8_t*>(
          pgm_read_ptr(&sprite.patternSafeFrames[frame]));
      const uint8_t* rareOverlay = reinterpret_cast<const uint8_t*>(
          pgm_read_ptr(&sprite.rareOverlayFrames[frame]));
      const uint16_t* patternAnchors = reinterpret_cast<const uint16_t*>(
          pgm_read_ptr(&sprite.patternAnchorFrames[frame]));
      const uint32_t pixelCount = static_cast<uint32_t>(sprite.width) * sprite.height;
      for (uint32_t pixelIndex = 0; pixelIndex < pixelCount; ++pixelIndex) {
        const uint8_t role = readSemantic(semantic, pixelIndex);
        const bool patternSafe = readPatternSafe(safeMask, pixelIndex);
        const uint8_t rareCode = readRareOverlay(rareOverlay, pixelIndex);
        const uint16_t packedAnchor = pgm_read_word(&patternAnchors[pixelIndex]);
        const uint16_t patternX = packedAnchor >> 7;
        const uint16_t patternY = packedAnchor & 0x7F;
        const uint16_t sourceX = pixelIndex % sprite.width;
        const uint16_t sourceY = pixelIndex / sprite.width;
        const uint8_t probedRole = applyTextureProbeRole(
            role, patternSafe, sourceX, sourceY, frame);
        if (patternSafe) {
          ++safePixels;
          if (role == 0) ++invalidSafePixels;
          if (role != probedRole) ++exercisedPixels;
        } else if (role != 0) {
          ++protectedPixels;
        }
        if (!patternSafe && role != probedRole) ++protectedChanges;

        for (uint8_t pattern = 1; pattern < kPatternCount; ++pattern) {
          const uint8_t treatedRole = applyCreatureTreatmentRole(
              role, patternSafe, rareCode, static_cast<PatternStyle>(pattern),
              kSelfTestSeed, false, patternX, patternY);
          if (patternSafe && role != treatedRole) {
            ++patternExercised[pattern];
            ++framePatternExercised[pattern];
          }
          if (!patternSafe && role != treatedRole) {
            ++patternProtectedChanges[pattern];
          }
        }

        const uint8_t rareRole = applyCreatureTreatmentRole(
            role, patternSafe, rareCode, PatternStyle::kSolid,
            kSelfTestSeed, true, patternX, patternY);
        // A non-zero rare code is the build-time authorization. It may live in
        // anatomy intentionally protected from common procedural textures.
        if (rareCode != 0 && role != rareRole) {
          ++rareExercised;
          ++frameRareExercised;
        }
        if (rareCode == 0 && role != rareRole) ++rareProtectedChanges;
      }
      for (uint8_t pattern = 1; pattern < kPatternCount; ++pattern) {
        if (framePatternExercised[pattern] == 0) ++missingPatternFrames;
      }
      if (frameRareExercised == 0) ++missingRareFrames;
    }
  }
  uint32_t treatmentProtectedChanges = rareProtectedChanges;
  bool everyPatternExercised = true;
  for (uint8_t pattern = 1; pattern < kPatternCount; ++pattern) {
    treatmentProtectedChanges += patternProtectedChanges[pattern];
    everyPatternExercised &= patternExercised[pattern] > 0;
  }
  const bool passed = safePixels > 0 && protectedPixels > 0 && exercisedPixels > 0 &&
                      invalidSafePixels == 0 && protectedChanges == 0 &&
                      everyPatternExercised && rareExercised > 0 &&
                      treatmentProtectedChanges == 0 && missingPatternFrames == 0 &&
                      missingRareFrames == 0;
  USBSerial.printf("[selftest] %s creatures=%u frames=%u safe=%lu protected=%lu exercised=%lu invalid_safe=%lu protected_changes=%lu\n",
                   passed ? "PASS" : "FAIL", kCreatureCount,
                   static_cast<unsigned>(kCreatureCount) * kFrameCount,
                   static_cast<unsigned long>(safePixels),
                   static_cast<unsigned long>(protectedPixels),
                   static_cast<unsigned long>(exercisedPixels),
                   static_cast<unsigned long>(invalidSafePixels),
                   static_cast<unsigned long>(protectedChanges));
  USBSerial.printf("[selftest] treatments spots=%lu stripes=%lu mottle=%lu rare=%lu treatment_protected_changes=%lu missing_pattern_frames=%u missing_rare_frames=%u\n",
                   static_cast<unsigned long>(patternExercised[static_cast<uint8_t>(PatternStyle::kSpots)]),
                   static_cast<unsigned long>(patternExercised[static_cast<uint8_t>(PatternStyle::kStripes)]),
                   static_cast<unsigned long>(patternExercised[static_cast<uint8_t>(PatternStyle::kMottle)]),
                   static_cast<unsigned long>(rareExercised),
                   static_cast<unsigned long>(treatmentProtectedChanges),
                   missingPatternFrames, missingRareFrames);
}

void readControls() {
  bool changed = false;
  while (USBSerial.available()) {
    const char command = static_cast<char>(USBSerial.read());
    if (command == 'c' || command == 'C') {
      creatureIndex = (creatureIndex + 1) % kCreatureCount;
      autoAdvance = false;
      changed = true;
    } else if (command == 'p' || command == 'P') {
      paletteIndex = (paletteIndex + 1) % kPaletteCount;
      autoAdvance = false;
      changed = true;
    } else if (command == 't' || command == 'T') {
      // Procedural treatments and authored rare motifs are mutually exclusive.
      // Cycling a common treatment exits rare mode; enabling rare below always
      // restores the required solid base.
      rareEnabled = false;
      patternStyle = static_cast<PatternStyle>(
          (static_cast<uint8_t>(patternStyle) + 1) % kPatternCount);
      autoAdvance = false;
      changed = true;
    } else if (command == 'r' || command == 'R') {
      rareEnabled = !rareEnabled;
      if (rareEnabled) patternStyle = PatternStyle::kSolid;
      autoAdvance = false;
      changed = true;
    } else if (command == 's' || command == 'S') {
      advancePatternSeed();
      autoAdvance = false;
      changed = true;
    } else if (command == 'd' || command == 'D') {
      renderMode = static_cast<RenderMode>((static_cast<uint8_t>(renderMode) + 1) % 3);
      autoAdvance = false;
      changed = true;
    } else if (command == 'h' || command == 'H') {
      animationFrozen = !animationFrozen;
      if (animationFrozen) frozenFrame = (millis() / 180) % kFrameCount;
      changed = true;
    } else if (command == 'a' || command == 'A') {
      autoAdvance = !autoAdvance;
      lastAutoAdvanceAtMs = millis();
      changed = true;
    } else if (command == 'v' || command == 'V') {
      runProtectionSelfTest();
    } else if (command == '?') {
      printHelp();
      printStatus();
    }
  }
  if (changed) printStatus();
}

void updateAutoAdvance(uint32_t now) {
  if (!autoAdvance || now - lastAutoAdvanceAtMs < kAutoAdvanceIntervalMs) return;
  lastAutoAdvanceAtMs = now;
  paletteIndex = (paletteIndex + 1) % kPaletteCount;
  if (paletteIndex == 0) creatureIndex = (creatureIndex + 1) % kCreatureCount;
  printStatus();
}

void drawCreature(uint32_t now) {
  uint16_t* framebuffer = gfx->getFramebuffer();
  const uint8_t frame = animationFrozen ? frozenFrame : (now / 180) % kFrameCount;
  const float drift = sinf(static_cast<float>(now) * 0.0022f);
  const CreatureSprite& sprite = *kCreatures[creatureIndex];
  const int16_t displayWidth = sprite.width * sprite.renderScale;
  const int16_t displayHeight = sprite.height * sprite.renderScale;
  const int16_t x = (LCD_WIDTH - displayWidth) / 2 +
                    static_cast<int16_t>(drift * (animationFrozen ? 0.0f : 5.0f));
  const int16_t y = (LCD_HEIGHT - displayHeight) / 2 +
                    static_cast<int16_t>(drift * (animationFrozen ? 0.0f : 8.0f));
  const PatternStyle effectivePattern =
      rareEnabled ? PatternStyle::kSolid : patternStyle;
  drawSemanticFrame(framebuffer, LCD_WIDTH, LCD_HEIGHT, sprite, frame, paletteIndex,
                    renderMode, x, y, effectivePattern, patternSeed, rareEnabled);

  gfx->setTextSize(1);
  gfx->setTextColor(0xE71C);
  gfx->setCursor(8, 9);
  gfx->print(sprite.label);
  gfx->print(" / ");
  gfx->print(kPaletteNames[paletteIndex]);
  gfx->setCursor(8, 424);
  gfx->print(renderModeName());
  gfx->print(" / ");
  gfx->print(patternStyleName(effectivePattern));
  if (rareEnabled) {
    gfx->print(" / RARE ");
    gfx->print(sprite.rareTreatmentLabel);
  }
  if (animationFrozen) gfx->print(" / HOLD");
}

void initializeDisplay() {
  Wire.begin(IIC_SDA, IIC_SCL);
  if (!expander.begin(0x20)) {
    USBSerial.println("[fatal] XCA9554 not found");
    while (true) delay(1000);
  }
  for (uint8_t pin = 0; pin < 3; ++pin) {
    expander.pinMode(pin, OUTPUT);
    expander.digitalWrite(pin, HIGH);
  }
  delay(20);
  if (!panel->begin()) {
    USBSerial.println("[fatal] CO5300 display initialization failed");
    while (true) delay(1000);
  }
  panel->setBrightness(kDisplayBrightness);
  if (!gfx->begin(GFX_SKIP_OUTPUT_BEGIN)) {
    USBSerial.println("[fatal] off-screen framebuffer allocation failed");
    while (true) delay(1000);
  }
}

void setup() {
  USBSerial.begin(115200);
  USBSerial.setTxTimeoutMs(0);
  initializeDisplay();
  lastAutoAdvanceAtMs = millis();
  USBSerial.printf("[boot] semantic reef demo; creatures=%u palettes=%u patterns=%u frames=%u psram=%u\n",
                   kCreatureCount, kPaletteCount, kPatternCount, kFrameCount,
                   ESP.getPsramSize());
  printHelp();
  printStatus();
  runProtectionSelfTest();
}

void loop() {
  const uint32_t now = millis();
  readControls();
  updateAutoAdvance(now);
  if (now - lastFrameAtMs < kFrameIntervalMs) {
    delay(4);
    return;
  }
  lastFrameAtMs = now;
  drawWater(now);
  drawCreature(now);
  // Match the production phonics app's no-tearing rule: only complete frames
  // are transferred to the AMOLED.
  gfx->flush();
}
