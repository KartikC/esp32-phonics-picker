#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_XCA9554.h>
#include "Arduino_DriveBus_Library.h"
#include "Arduino_GFX_Library.h"
#include "HWCDC.h"
#include "SensorQMI8658.hpp"
#include "pin_config.h"
#include "esp_err.h"
#include "esp_random.h"
#include "esp_sleep.h"

#include "AudioPlan.h"
#include "CardStoneAsset.h"
#include "CreatureRewardSelector.h"
#include "GameEngine.h"
#include "LayoutGeometry.h"
#include "MaintenanceMuteController.h"
#include "RewardAudioSelector.h"
#include "RewardTransition.h"
#include "../CreatureAssets/GeneratedCreatureVariations.h"
#include "fonts/AtkinsonHyperlegibleNextExtraBold112.h"

using namespace phonics_game;
using namespace creature_variations;

static_assert(kCreatureCount == CreatureRewardSelector::kCreatureCount,
              "selector and generated creature roster must stay aligned");
static_assert(kCreatureCount == AudioPlan::creatureSfxCount(),
              "creature visuals and sound roster must stay aligned");
static_assert(RewardAudioSelector::kBubbleCount == AudioPlan::bubbleSfxCount(),
              "bubble selector and sound roster must stay aligned");
static_assert(kGlassSquidIndex ==
                  static_cast<uint8_t>(RewardCreature::kGlassSquid) &&
              kAnglerfishIndex ==
                  static_cast<uint8_t>(RewardCreature::kAnglerfish) &&
              kSeaAngelIndex ==
                  static_cast<uint8_t>(RewardCreature::kSeaAngel) &&
              kGulperEelIndex ==
                  static_cast<uint8_t>(RewardCreature::kGulperEel),
              "generated and selector creature ordinals must stay aligned");

HWCDC& USBSerial = HWCDCSerial;
Adafruit_XCA9554 expander;
SensorQMI8658 qmi;

Arduino_DataBus* displayBus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_CO5300* panel = new Arduino_CO5300(
    displayBus, GFX_NOT_DEFINED, 0, LCD_WIDTH, LCD_HEIGHT, 16, 0, 0, 0);
Arduino_Canvas* gfx = new Arduino_Canvas(
    LCD_WIDTH, LCD_HEIGHT, panel);

std::shared_ptr<Arduino_IIC_DriveBus> touchBus =
    std::make_shared<Arduino_HWIIC>(IIC_SDA, IIC_SCL, &Wire);
void onTouchInterrupt();
std::unique_ptr<Arduino_IIC> touch(new Arduino_CST816x(
    touchBus, CST816T_DEVICE_ADDRESS, DRIVEBUS_DEFAULT_VALUE, TP_INT, onTouchInterrupt));

GameEngine game(1);
CreatureRewardSelector rewardSelector(1);
RewardAudioSelector rewardAudioSelector(1);
CreatureRewardPlan activeReward{};
MaintenanceMuteController maintenanceMute;

constexpr uint16_t kMoonlight = 0xEF5C;
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint8_t kDisplayBrightness = 190;
constexpr uint8_t kPowerButtonPin = 4;
constexpr uint32_t kPowerDebounceMs = 50;
constexpr uint32_t kSoftwareShortPressMaxMs = 1500;
constexpr uint32_t kMotionSampleMs = 80;
constexpr uint8_t kAxp2101Address = 0x34;
constexpr uint32_t kBatterySampleMs = 30000;
constexpr uint32_t kAwakePowerPollMs = 20;
// GPIO21 normally provides immediate touch IRQs. A 64 ms safety poll keeps a
// failed/missed edge below a perceptible tap-latency threshold while still
// removing most of the former 8 ms idle I2C traffic.
constexpr uint32_t kTouchSafetyPollMs = 64;
// PWR is behind the TCA9554 and its INT output is not routed to the ESP32-S3,
// so standby must wake briefly to poll it. Fifty milliseconds preserves the
// existing debounce cadence while clock-gating both CPU cores between polls.
constexpr uint64_t kStandbyPollUs = 50000;
bool touchWasDown = false;
volatile bool touchInterruptPending = false;
bool touchInterruptGateAvailable = false;
uint32_t touchPollCount = 0;
uint32_t lastTouchSafetyPollMs = 0;
uint16_t lastCelebrationFrame = 0xffff;
uint32_t lastMotionSampleMs = 0;
float neutralAccelX = 0.0f;
float neutralAccelY = 0.0f;
float filteredAccelX = 0.0f;
float filteredAccelY = 0.0f;
float easedLeftSlideX = 0.0f;
float easedLeftSlideY = 0.0f;
float easedRightSlideX = 0.0f;
float easedRightSlideY = 0.0f;
float leftMotionEase = 0.115f;
float rightMotionEase = 0.125f;
bool motionReady = false;
bool imuAvailable = false;
int16_t leftSlideX = 0;
int16_t leftSlideY = 0;
int16_t rightSlideX = 0;
int16_t rightSlideY = 0;
bool previewMode = false;
bool animatedRewardPreview = false;
uint32_t animatedRewardPreviewStartedAtMs = 0;
uint16_t lastAnimatedRewardPreviewFrame = 0xffff;
bool standbyMode = false;
bool usbDataConnected = false;
bool powerButtonAvailable = false;
bool awaitingTouchRelease = false;
bool powerRawPressed = false;
bool powerStablePressed = false;
bool powerButtonArmed = false;
bool powerPressActive = false;
bool standbyImuSuspended = false;
bool standbySleepFailureReported = false;
uint32_t powerRawChangedAtMs = 0;
uint32_t powerPressedAtMs = 0;
uint32_t lastPowerPollMs = 0;
uint32_t powerPollCount = 0;

struct BatteryState {
  bool valid = false;
  bool connected = false;
  bool usb = false;
  bool charging = false;
  uint8_t percent = 0;
  uint8_t chargerState = 0;
  uint16_t millivolts = 0;
};

BatteryState batteryState;
uint32_t lastBatterySampleMs = 0;
bool batteryVisualDirty = false;

enum class ForcedRewardMode : uint8_t { none, common, rare };
ForcedRewardMode forcedRewardMode = ForcedRewardMode::none;

void ARDUINO_ISR_ATTR onTouchInterrupt() {
  touchInterruptPending = true;
}

bool readPmicRegister(uint8_t address, uint8_t& value) {
  Wire.beginTransmission(kAxp2101Address);
  Wire.write(address);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(kAxp2101Address, static_cast<uint8_t>(1)) != 1) return false;
  value = Wire.read();
  return true;
}

uint8_t batteryTier(const BatteryState& state) {
  if (!state.valid || !state.connected) return 0;
  if (state.percent >= 60) return 3;
  if (state.percent >= 25) return 2;
  return 1;
}

bool sampleBattery(uint32_t now) {
  uint8_t status1 = 0;
  uint8_t status2 = 0;
  uint8_t voltageHigh = 0;
  uint8_t voltageLow = 0;
  uint8_t percent = 0;
  if (!readPmicRegister(0x00, status1) ||
      !readPmicRegister(0x01, status2) ||
      !readPmicRegister(0x34, voltageHigh) ||
      !readPmicRegister(0x35, voltageLow) ||
      !readPmicRegister(0xA4, percent)) {
    batteryState.valid = false;
    batteryVisualDirty = true;
    lastBatterySampleMs = now;
    return false;
  }

  const BatteryState previous = batteryState;
  batteryState.valid = true;
  batteryState.connected = (status1 & (1u << 3)) != 0;
  const bool vbusGood = (status1 & (1u << 5)) != 0;
  batteryState.usb = vbusGood && (status2 & (1u << 3)) == 0;
  const uint8_t powerState = status2 >> 5;
  batteryState.charging = powerState == 1;
  batteryState.percent = batteryState.connected ? percent : 0;
  batteryState.chargerState = status2 & 0x07;
  batteryState.millivolts = batteryState.connected ?
      (static_cast<uint16_t>(voltageHigh & 0x1f) << 8) | voltageLow
      : 0;
  lastBatterySampleMs = now;
  if (!previous.valid ||
      batteryTier(previous) != batteryTier(batteryState)) {
    batteryVisualDirty = true;
  }
  return true;
}

void reportBattery() {
  if (!sampleBattery(millis())) {
    USBSerial.println("[battery] pmic=unavailable");
    return;
  }
  const char* chargerStates[] = {
      "tri-charge", "pre-charge", "constant-current", "constant-voltage",
      "reserved", "done", "stopped", "reserved"};
  USBSerial.printf(
      "[battery] connected=%s percent=%u voltage_mv=%u usb=%s charging=%s "
      "charger=%s\n",
      batteryState.connected ? "yes" : "no", batteryState.percent,
      batteryState.millivolts, batteryState.usb ? "yes" : "no",
      batteryState.charging ? "yes" : "no",
      chargerStates[batteryState.chargerState]);
}

uint16_t blend565(uint16_t foreground, uint16_t background, uint8_t amount) {
  const uint16_t fr = (foreground >> 11) & 0x1f;
  const uint16_t fg = (foreground >> 5) & 0x3f;
  const uint16_t fb = foreground & 0x1f;
  const uint16_t br = (background >> 11) & 0x1f;
  const uint16_t bg = (background >> 5) & 0x3f;
  const uint16_t bb = background & 0x1f;
  const uint16_t r = (fr * amount + br * (255 - amount)) / 255;
  const uint16_t g = (fg * amount + bg * (255 - amount)) / 255;
  const uint16_t b = (fb * amount + bb * (255 - amount)) / 255;
  return static_cast<uint16_t>((r << 11) | (g << 5) | b);
}

void drawBackground() {
  // AMOLED pixels outside the learning objects are physically off.
  gfx->fillScreen(0x0000);
}

uint16_t pack565(uint8_t red, uint8_t green, uint8_t blue) {
  return static_cast<uint16_t>(((red & 0xF8) << 8) |
                               ((green & 0xFC) << 3) |
                               (blue >> 3));
}

void drawRewardWater(uint32_t elapsed) {
  uint16_t* framebuffer = gfx->getFramebuffer();
  for (int16_t y = 0; y < LCD_HEIGHT; ++y) {
    const uint8_t red = 5 + (2 * y) / LCD_HEIGHT;
    const uint8_t green = 39 - (20 * y) / LCD_HEIGHT;
    const uint8_t blue = 58 - (24 * y) / LCD_HEIGHT;
    uint16_t color = pack565(red, green, blue);
    // A restrained moving caustic band keeps the reward water alive without
    // introducing a new hue or competing with the creature.
    if (((y + elapsed / 24) % 38) < 2) {
      color = blend565(0x4EBC, color, 26);
    }
    uint16_t* row = framebuffer + static_cast<uint32_t>(y) * LCD_WIDTH;
    for (int16_t x = 0; x < LCD_WIDTH; ++x) row[x] = color;
  }

  // Quiet seabed shapes only. The former stationary colored circles are
  // intentionally absent from both the demo and this reward scene.
  gfx->fillTriangle(0, 407, 83, 389, 168, LCD_HEIGHT, 0x08C6);
  gfx->fillTriangle(112, LCD_HEIGHT, 237, 393, LCD_WIDTH, LCD_HEIGHT, 0x08C6);

  constexpr int16_t bubbleX[] = {36, 49, 319, 330, 286};
  constexpr int16_t bubbleBaseY[] = {112, 88, 182, 151, 274};
  for (uint8_t index = 0; index < 5; ++index) {
    const int16_t travel = static_cast<int16_t>(
        (elapsed / (36 + index * 7)) % 48);
    const int16_t y = bubbleBaseY[index] - travel;
    gfx->drawCircle(bubbleX[index], y, index % 2 ? 2 : 3, 0x2E99);
  }
}

void clipRewardAtSurface(int16_t surfaceY, uint32_t elapsed) {
  if (surfaceY >= LCD_HEIGHT) {
    gfx->fillScreen(0x0000);
    return;
  }
  if (surfaceY > 0) gfx->fillRect(0, 0, LCD_WIDTH, surfaceY, 0x0000);
  constexpr int8_t wave[] = {0, 1, 2, 1, 0, -1, -2, -1};
  const uint8_t phase = (elapsed / 45) % 8;
  for (int16_t x = 0; x < LCD_WIDTH; ++x) {
    const int16_t y = surfaceY + wave[(x / 7 + phase) % 8];
    if (y >= 0 && y < LCD_HEIGHT) gfx->drawPixel(x, y, 0x4EBC);
  }
}

void drawCreatureName(const char* label) {
  constexpr int16_t kLabelCenterY = LCD_HEIGHT - 21;
  int16_t boundsX = 0;
  int16_t boundsY = 0;
  uint16_t width = 0;
  uint16_t height = 0;
  gfx->setFont(nullptr);
  gfx->setTextSize(2);
  gfx->getTextBounds(label, 0, 0, &boundsX, &boundsY, &width, &height);
  const int16_t cursorX = (LCD_WIDTH - static_cast<int16_t>(width)) / 2 -
                          boundsX;
  const int16_t cursorY = kLabelCenterY - static_cast<int16_t>(height) / 2 -
                          boundsY;
  const int16_t boxX = cursorX + boundsX - 7;
  const int16_t boxY = cursorY + boundsY - 4;
  gfx->fillRoundRect(boxX, boxY, width + 14, height + 8, 6, 0x0208);
  gfx->drawRoundRect(boxX, boxY, width + 14, height + 8, 6, 0x2E99);
  gfx->setCursor(cursorX, cursorY);
  gfx->setTextColor(0xE71C);
  gfx->print(label);
  gfx->setTextSize(1);
}

void drawCreatureReward(uint32_t elapsed, uint8_t creatureIndex,
                        uint8_t paletteIndex, uint8_t patternIndex,
                        uint32_t patternSeed, bool rare,
                        uint32_t renderElapsed = UINT32_MAX) {
  if (renderElapsed == UINT32_MAX) renderElapsed = elapsed;
  drawRewardWater(renderElapsed);
  const int16_t surfaceY = rewardWaterSurfaceY(elapsed, LCD_HEIGHT);
  const CreatureSprite* visibleSprite = nullptr;
  if (rewardCreatureVisible(elapsed)) {
    const CreatureSprite& sprite = *kCreatures[creatureIndex % kCreatureCount];
    visibleSprite = &sprite;
    const uint8_t frame = static_cast<uint8_t>(
        ((renderElapsed - kWaterRiseEndMs) / 110) % kFrameCount);
    const int16_t displayWidth = sprite.width * sprite.renderScale;
    const int16_t displayHeight = sprite.height * sprite.renderScale;
    constexpr int16_t kLabelBandTop = LCD_HEIGHT - 40;
    constexpr int8_t kSharkBiteLunge[kFrameCount] = {0, 2, 5, 2};
    const int16_t biteLunge =
        creatureIndex % kCreatureCount == kReefSharkIndex
            ? static_cast<int16_t>(kSharkBiteLunge[frame])
            : 0;
    const int16_t destinationX = (LCD_WIDTH - displayWidth) / 2 + biteLunge;
    const int16_t destinationY = (kLabelBandTop - displayHeight) / 2 + 2;
    drawSemanticFrame(
        gfx->getFramebuffer(), LCD_WIDTH, LCD_HEIGHT, sprite, frame,
        paletteIndex, RenderMode::kColor, destinationX, destinationY,
        static_cast<PatternStyle>(patternIndex % kPatternCount), patternSeed,
        rare);

    if (rare && sprite.celebrationSparkles) {
      const uint16_t sparkle = blend565(0xFFE0, 0xFFFF, 150);
      for (uint8_t index = 0; index < 3; ++index) {
        const uint32_t hash = patternSeed * (index + 3) + 0x9E3779B9u;
        const int16_t x = 34 + static_cast<int16_t>(hash % (LCD_WIDTH - 68));
        const int16_t y = 58 + static_cast<int16_t>(
            ((hash >> 9) + renderElapsed / 9) % 270);
        const int16_t radius = 2 + ((renderElapsed / 120 + index) & 1);
        gfx->drawFastHLine(x - radius, y, radius * 2 + 1, sparkle);
        gfx->drawFastVLine(x, y - radius, radius * 2 + 1, sparkle);
      }
    }
  }
  // Apply the rising/receding surface after the creature so it emerges from
  // and returns behind the same continuous water layer.
  clipRewardAtSurface(surfaceY, renderElapsed);
  // The name is part of the complete creature-visible contract. Overlay it
  // after the receding surface so it remains adult-legible through the final
  // recede frame instead of being clipped a few frames early.
  if (visibleSprite != nullptr) drawCreatureName(visibleSprite->label);
  gfx->flush();
}

CardRect cardRect(bool left, uint8_t layoutVariant, int16_t pulse = 0) {
  return makeCardRect(left, layoutVariant,
                      left ? leftSlideX : rightSlideX,
                      left ? leftSlideY : rightSlideY, pulse);
}

void drawCentered(const char* text, int16_t centerX, int16_t centerY,
                  const GFXfont* font, uint16_t color) {
  int16_t x1, y1;
  uint16_t w, h;
  gfx->setFont(font);
  gfx->setTextSize(1);
  gfx->getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  gfx->setCursor(centerX - x1 - static_cast<int16_t>(w / 2),
                 centerY - y1 - static_cast<int16_t>(h / 2));
  gfx->setTextColor(color);
  gfx->print(text);
}

uint8_t stoneRoleForLocalPixel(const CardRect& card,
                               int16_t localX, int16_t localY) {
  if (localX < 0 || localY < 0 || localX >= card.w || localY >= card.h) {
    return kStoneTransparent;
  }
  const uint16_t sourceX = static_cast<uint16_t>(
      static_cast<uint32_t>(localX) * kStoneSourceWidth / card.w);
  const uint16_t sourceY = static_cast<uint16_t>(
      static_cast<uint32_t>(localY) * kStoneSourceHeight / card.h);
  return stoneRoleAt(sourceX, sourceY);
}

void drawStoneCardBody(const CardRect& card, uint16_t baseColor,
                       bool pulsing) {
  // These blends are the RGB565 equivalent of the approved v4 contact-sheet
  // treatment. Only the two broad body planes receive the letter's full tint;
  // the remaining six mineral roles keep the source stone's cool identity.
  const uint16_t mainBody = blend565(
      baseColor, 0x0000, pulsing ? 215 : 199);
  uint16_t roleColors[kStoneRoleCount] = {};
  roleColors[kStoneMainBody] = mainBody;
  roleColors[kStoneBodyShadow] = blend565(mainBody, 0x0000, 199);
  roleColors[kStoneDeepCrevice] =
      blend565(pack565(11, 42, 60), mainBody, 217);
  roleColors[kStonePaleMineral] =
      blend565(pack565(216, 238, 240), mainBody, 189);
  roleColors[kStoneDeepSlate] =
      blend565(pack565(18, 74, 96), mainBody, 196);
  roleColors[kStoneMidMineral] =
      blend565(pack565(145, 183, 190), mainBody, 178);
  roleColors[kStoneWhiteChip] = pack565(247, 255, 255);
  roleColors[kStoneCyanGlint] =
      blend565(pack565(39, 211, 208), mainBody, 242);

  uint16_t* framebuffer = gfx->getFramebuffer();
  // The shadow offset is positive in both axes. Writing it immediately before
  // each source pixel is safe in top-to-bottom order: later opaque body pixels
  // cover the shadow, while the irregular perimeter and chipped notches retain
  // the exact silhouette. This halves semantic-map lookups during tilt redraws.
  for (int16_t localY = 0; localY < card.h; ++localY) {
    const int16_t destinationY = card.y + localY;
    const uint16_t sourceY = static_cast<uint16_t>(
        static_cast<uint32_t>(localY) * kStoneSourceHeight / card.h);
    for (int16_t localX = 0; localX < card.w; ++localX) {
      const uint16_t sourceX = static_cast<uint16_t>(
          static_cast<uint32_t>(localX) * kStoneSourceWidth / card.w);
      const uint8_t role = stoneRoleAt(sourceX, sourceY);
      if (role == kStoneTransparent) continue;
      const int16_t shadowX = card.x + kCardShadowX + localX;
      const int16_t shadowY = card.y + kCardShadowY + localY;
      if (shadowX >= 0 && shadowX < LCD_WIDTH &&
          shadowY >= 0 && shadowY < LCD_HEIGHT) {
        framebuffer[static_cast<uint32_t>(shadowY) * LCD_WIDTH + shadowX] =
            kStoneShadowColor;
      }
      const int16_t destinationX = card.x + localX;
      if (destinationX >= 0 && destinationX < LCD_WIDTH &&
          destinationY >= 0 && destinationY < LCD_HEIGHT) {
        framebuffer[static_cast<uint32_t>(destinationY) * LCD_WIDTH +
                    destinationX] = roleColors[role];
      }
    }
  }
}

void drawStoneMotifPixel(const CardRect& card, int16_t x, int16_t y,
                         uint16_t color) {
  const int16_t localX = x - card.x;
  const int16_t localY = y - card.y;
  if (stoneRoleForLocalPixel(card, localX, localY) != kStoneMainBody) return;
  if (x < 0 || x >= LCD_WIDTH || y < 0 || y >= LCD_HEIGHT) return;
  gfx->getFramebuffer()[static_cast<uint32_t>(y) * LCD_WIDTH + x] = color;
}

void drawStoneMotifLine(const CardRect& card, int16_t x0, int16_t y0,
                        int16_t x1, int16_t y1, uint16_t color) {
  int16_t dx = abs(x1 - x0);
  const int16_t stepX = x0 < x1 ? 1 : -1;
  const int16_t dy = -abs(y1 - y0);
  const int16_t stepY = y0 < y1 ? 1 : -1;
  int16_t error = dx + dy;
  while (true) {
    drawStoneMotifPixel(card, x0, y0, color);
    if (x0 == x1 && y0 == y1) break;
    const int16_t doubled = error * 2;
    if (doubled >= dy) {
      error += dy;
      x0 += stepX;
    }
    if (doubled <= dx) {
      error += dx;
      y0 += stepY;
    }
  }
}

void drawStoneMotifShape(const CardRect& card, uint8_t family, uint8_t index,
                         int16_t x, int16_t y, uint16_t color) {
  switch (family) {
    case 0: {
      const int16_t radius = 2 + (index % 2);
      for (int16_t dy = -radius; dy <= radius; ++dy) {
        for (int16_t dx = -radius; dx <= radius; ++dx) {
          if (dx * dx + dy * dy <= radius * radius) {
            drawStoneMotifPixel(card, x + dx, y + dy, color);
          }
        }
      }
      drawStoneMotifPixel(card, x + 4, y - 3, color);
      break;
    }
    case 1:
      drawStoneMotifLine(card, x - 4, y + 3, x + 4, y - 3, color);
      drawStoneMotifLine(card, x - 2, y + 4, x + 5, y - 1, color);
      break;
    case 2:
      drawStoneMotifLine(card, x - 3, y, x + 3, y, color);
      drawStoneMotifLine(card, x, y - 3, x, y + 3, color);
      drawStoneMotifPixel(card, x + 4, y + 3, color);
      break;
    default:
      drawStoneMotifLine(card, x - 2, y - 2, x + 2, y - 2, color);
      drawStoneMotifLine(card, x + 2, y - 2, x + 2, y + 2, color);
      drawStoneMotifLine(card, x + 2, y + 2, x - 2, y + 2, color);
      drawStoneMotifLine(card, x - 2, y + 2, x - 2, y - 2, color);
      drawStoneMotifPixel(card, x + 4, y - 3, color);
      break;
  }
}

void drawLetterTexture(const CardRect& card, char letter, uint16_t baseColor,
                       bool pulsing) {
  // The seed and motif depend only on the letter, so the visual anchor is
  // identical in every round and across restarts.
  uint32_t state = 0x9E3779B9u ^
                   (static_cast<uint32_t>(letter - 'a' + 1) * 0x45D9F3Bu);
  const uint16_t mainBody = blend565(
      baseColor, 0x0000, pulsing ? 215 : 199);
  const uint16_t lightIncision = blend565(
      mainBody, pack565(216, 238, 240), 230);
  const uint16_t darkIncision = blend565(mainBody, 0x0000, 214);
  const uint8_t family = static_cast<uint8_t>((letter - 'a') % 4);
  for (uint8_t i = 0; i < 13; ++i) {
    state = state * 1664525u + 1013904223u;
    const int16_t x = card.x + 17 +
                      static_cast<int16_t>((state >> 8) % (card.w - 34));
    state = state * 1664525u + 1013904223u;
    const int16_t y = card.y + 18 +
                      static_cast<int16_t>((state >> 8) % (card.h - 36));
    drawStoneMotifShape(card, family, i, x - 1, y - 1, lightIncision);
    drawStoneMotifShape(card, family, i, x, y, darkIncision);
  }
}

void drawCard(const CardRect& card, char letter, bool pulsing) {
  const uint16_t color = kStoneLetterColors[letter - 'a'];
  drawStoneCardBody(card, color, pulsing);
  drawLetterTexture(card, letter, color, pulsing);

  char label[] = {letter, '\0'};
  // Four-pass dark halo preserves the silhouette without burdening motion redraws.
  constexpr int8_t halo[][2] = {{-2, 0}, {2, 0}, {0, -2}, {0, 2}};
  const uint16_t haloColor = pack565(11, 42, 60);
  for (const auto& offset : halo) {
    drawCentered(label, card.x + card.w / 2 + offset[0],
                 card.y + card.h / 2 + offset[1],
                 &AtkinsonHyperlegibleNextExtraBold112,
                 haloColor);
  }
  drawCentered(label, card.x + card.w / 2, card.y + card.h / 2,
               &AtkinsonHyperlegibleNextExtraBold112, kWhite);
}

void drawReplayButton() {
  gfx->fillCircle(kReplayCenterX, kReplayCenterY, kReplayVisualRadius,
                  blend565(0x1CBF, 0x0000, 105));
  gfx->drawCircle(kReplayCenterX, kReplayCenterY, kReplayVisualRadius,
                  kMoonlight);
  gfx->drawCircle(kReplayCenterX, kReplayCenterY,
                  kReplayVisualRadius - 1, blend565(kWhite, 0x1CBF, 165));
  if (usbDataConnected && maintenanceMute.muted()) {
    // The mute indicator replaces the replay glyph only while a USB data host
    // is present; unplugging returns the child-facing screen to its usual UI.
    gfx->fillRect(kReplayCenterX - 12, kReplayCenterY - 5, 6, 10, kWhite);
    gfx->fillTriangle(kReplayCenterX - 6, kReplayCenterY - 9,
                      kReplayCenterX - 6, kReplayCenterY + 9,
                      kReplayCenterX + 2, kReplayCenterY + 5, kWhite);
    const uint16_t slash = 0xFBAE;
    gfx->drawLine(kReplayCenterX - 14, kReplayCenterY - 14,
                  kReplayCenterX + 14, kReplayCenterY + 14, slash);
    gfx->drawLine(kReplayCenterX - 13, kReplayCenterY - 14,
                  kReplayCenterX + 15, kReplayCenterY + 14, slash);
  } else {
    gfx->fillTriangle(kReplayCenterX - 8, kReplayCenterY - 11,
                      kReplayCenterX - 8, kReplayCenterY + 11,
                      kReplayCenterX + 11, kReplayCenterY, kWhite);
  }
}

void drawBatteryIndicator() {
  if (!batteryState.valid || !batteryState.connected) {
    batteryVisualDirty = false;
    return;
  }
  const uint8_t tier = batteryTier(batteryState);
  const uint16_t color = tier == 3 ? blend565(0x07E0, 0x0000, 145) :
                         tier == 2 ? blend565(0xFFE0, 0x0000, 155) :
                                     blend565(0xF800, 0x0000, 175);
  constexpr int16_t centerX = LCD_WIDTH / 2;
  constexpr int16_t centerY = 14;
  constexpr int16_t spacing = 11;
  const int16_t firstX = centerX - ((tier - 1) * spacing) / 2;
  for (uint8_t i = 0; i < tier; ++i) {
    gfx->fillCircle(firstX + i * spacing, centerY, 3, color);
  }
  batteryVisualDirty = false;
}

bool updateMotion(uint32_t now) {
  if (!imuAvailable || now - lastMotionSampleMs < kMotionSampleMs ||
      !qmi.getDataReady()) return false;
  lastMotionSampleMs = now;
  IMUdata acceleration;
  if (!qmi.getAccelerometer(acceleration.x, acceleration.y, acceleration.z)) {
    return false;
  }
  if (!motionReady) {
    neutralAccelX = filteredAccelX = acceleration.x;
    neutralAccelY = filteredAccelY = acceleration.y;
    motionReady = true;
    return false;
  }

  // Low-pass the sensor, then let each tile ease independently toward the same
  // gravity target. Per-round rates differ slightly, while the relative clamps
  // preserve the proven gap and keep the pair feeling coherent.
  filteredAccelX = filteredAccelX * 0.86f + acceleration.x * 0.14f;
  filteredAccelY = filteredAccelY * 0.86f + acceleration.y * 0.14f;
  const auto targetPixels = [](float delta, float scale, int16_t limit) {
    constexpr float deadZoneG = 0.025f;
    if (fabsf(delta) <= deadZoneG) return 0.0f;
    delta += delta > 0.0f ? -deadZoneG : deadZoneG;
    return constrain(delta * scale, -static_cast<float>(limit),
                     static_cast<float>(limit));
  };
  // The QMI8658 package is rotated clockwise relative to the portrait panel.
  // Live hardware observation confirms this screen-space transform: a right
  // tilt must move right and a down tilt must move down.
  const float screenHorizontalG = -(filteredAccelY - neutralAccelY);
  const float screenVerticalG = filteredAccelX - neutralAccelX;
  const float targetX = targetPixels(screenHorizontalG, 52.0f,
                                     kMaxTileSlideX);
  const float targetY = targetPixels(screenVerticalG, 70.0f,
                                     kMaxTileSlideY);
  easedLeftSlideX += (targetX - easedLeftSlideX) * leftMotionEase;
  easedLeftSlideY += (targetY - easedLeftSlideY) * leftMotionEase;
  easedRightSlideX += (targetX - easedRightSlideX) * rightMotionEase;
  easedRightSlideY += (targetY - easedRightSlideY) * rightMotionEase;

  const auto clampPair = [](float& left, float& right, float minDifference,
                            float maxDifference) {
    const float midpoint = (left + right) * 0.5f;
    const float halfDifference = constrain((right - left) * 0.5f,
                                           minDifference * 0.5f,
                                           maxDifference * 0.5f);
    left = midpoint - halfDifference;
    right = midpoint + halfDifference;
  };
  clampPair(easedLeftSlideX, easedRightSlideX,
            kMinHorizontalSlideSeparation,
            kMaxHorizontalSlideSeparation);
  clampPair(easedLeftSlideY, easedRightSlideY,
            -kMaxVerticalSlideSeparation, kMaxVerticalSlideSeparation);

  const int16_t nextLeftX = constrain(static_cast<int>(roundf(easedLeftSlideX)),
                                      -kMaxTileSlideX, kMaxTileSlideX);
  const int16_t nextLeftY = constrain(static_cast<int>(roundf(easedLeftSlideY)),
                                      -kMaxTileSlideY, kMaxTileSlideY);
  const int16_t roundedRightX = constrain(
      static_cast<int>(roundf(easedRightSlideX)),
      -kMaxTileSlideX, kMaxTileSlideX);
  const int16_t roundedRightY = constrain(
      static_cast<int>(roundf(easedRightSlideY)),
      -kMaxTileSlideY, kMaxTileSlideY);
  const int16_t nextRightX = nextLeftX + constrain(
      roundedRightX - nextLeftX, kMinHorizontalSlideSeparation,
      kMaxHorizontalSlideSeparation);
  const int16_t nextRightY = nextLeftY + constrain(
      roundedRightY - nextLeftY, -kMaxVerticalSlideSeparation,
      kMaxVerticalSlideSeparation);
  if (nextLeftX == leftSlideX && nextLeftY == leftSlideY &&
      nextRightX == rightSlideX && nextRightY == rightSlideY) return false;
  leftSlideX = nextLeftX;
  leftSlideY = nextLeftY;
  rightSlideX = nextRightX;
  rightSlideY = nextRightY;
  return true;
}

void randomizeMotionRates() {
  const uint32_t random = esp_random();
  leftMotionEase = 0.105f + static_cast<float>(random & 0x0f) * 0.0015f;
  rightMotionEase = 0.105f + static_cast<float>((random >> 8) & 0x0f) * 0.0015f;
  if (fabsf(leftMotionEase - rightMotionEase) < 0.006f) {
    rightMotionEase = rightMotionEase < 0.117f ?
        rightMotionEase + 0.008f : rightMotionEase - 0.008f;
  }
}

void drawRound(int16_t correctPulse = 0) {
  drawBackground();
  drawReplayButton();
  drawBatteryIndicator();
  const Round& round = game.round();
  const char leftLetter = GameEngine::letter(round.targetOnLeft ? round.target : round.distractor);
  const char rightLetter = GameEngine::letter(round.targetOnLeft ? round.distractor : round.target);
  const bool pulseLeft = game.celebrating() && round.targetOnLeft;
  const bool pulseRight = game.celebrating() && !round.targetOnLeft;
  drawCard(cardRect(true, round.layoutVariant, pulseLeft ? correctPulse : 0), leftLetter, pulseLeft);
  drawCard(cardRect(false, round.layoutVariant, pulseRight ? correctPulse : 0), rightLetter, pulseRight);
  // Compose completely off-screen, then transfer one finished frame. Never
  // expose clearing, texture, or glyph drawing as intermediate AMOLED states.
  gfx->flush();
}

bool replayCurrentPrompt(uint32_t now) {
  if (!game.replay(now)) return false;
  const Round& round = game.round();
  const char target = GameEngine::letter(round.target);
  AudioPlan::initial(round.promptVariant, target);
  USBSerial.printf("[replay] prompt=%u target=%c volume=%u\n",
                   round.promptVariant, target, kAudioVolumePercent);
  return true;
}

bool syncAudioGate() {
  if (standbyMode || maintenanceMute.muted()) return AudioPlan::suspend();
  return AudioPlan::resume();
}

void handleMaintenanceMuteEvent(MaintenanceMuteEvent event, uint32_t now) {
  if (event == MaintenanceMuteEvent::none) return;
  if (event == MaintenanceMuteEvent::replay) {
    // A disconnect can mature a pending replay at the same moment it clears
    // maintenance mute. Reconcile the physical audio gate before handling the
    // replay so controller state and codec/PA state can never diverge.
    syncAudioGate();
    if (!standbyMode && !previewMode && !replayCurrentPrompt(now)) {
      USBSerial.println("[replay] unavailable during celebration");
    }
    return;
  }

  const bool audioStateApplied = syncAudioGate();
  USBSerial.printf("[mute] state=%s usb_data=%s audio=%s\n",
                   maintenanceMute.muted() ? "on" : "off",
                   usbDataConnected ? "yes" : "no",
                   audioStateApplied ? "ok" : "FAILED-safe");
  if (!standbyMode && !previewMode && !game.celebrating()) drawRound();
}

void pollMaintenanceMute(uint32_t now) {
  const MaintenanceMuteEvent event =
      maintenanceMute.update(now, USBSerial.isPlugged());
  const bool effectiveConnection = maintenanceMute.dataConnected();
  const bool connectionChanged = effectiveConnection != usbDataConnected;
  usbDataConnected = effectiveConnection;
  handleMaintenanceMuteEvent(event, now);
  if (connectionChanged && event != MaintenanceMuteEvent::toggled &&
      !standbyMode && !previewMode &&
      !game.celebrating()) {
    drawRound();
  }
}

void setStandby(bool enabled, uint32_t now) {
  if (enabled == standbyMode) return;
  if (enabled) {
    maintenanceMute.cancelPending();
    standbyMode = true;
    game.suspend(now);
    const bool audioQuiet = syncAudioGate();
    standbyImuSuspended = imuAvailable && qmi.disableAccelerometer();
    panel->setBrightness(0);
    panel->displayOff();
    touchWasDown = false;
    USBSerial.printf("[power] standby; audio=%s imu=%s sleep=%s\n",
                     audioQuiet ? "powered-down" : "muted-with-warning",
                     !imuAvailable ? "unavailable" :
                     (standbyImuSuspended ? "off" : "warning"),
                     usbDataConnected ? "usb-polled" : "light");
    return;
  }

  panel->setBrightness(0);
  panel->displayOn();
  standbyMode = false;
  // Recompose a normal round while the panel is still dark. Mute or USB-data
  // state may have changed while asleep, and flushing the retained framebuffer
  // would otherwise expose a stale replay/mute icon on wake.
  if (!previewMode && !game.celebrating()) {
    drawRound();
  } else {
    gfx->flush();
  }
  const bool audioReady = syncAudioGate();
  if (standbyImuSuspended) {
    if (!qmi.enableAccelerometer()) {
      USBSerial.println("[power] warning: accelerometer resume failed");
      imuAvailable = false;
    }
    standbyImuSuspended = false;
    motionReady = false;
    lastMotionSampleMs = millis();
  }
  panel->setBrightness(kDisplayBrightness);
  // A USB preview owns a separate pause. Waking the panel must not restart
  // the game clock behind a held or animated camera-inspection frame.
  if (!previewMode) game.resume(millis());
  awaitingTouchRelease = true;
  touchWasDown = true;
  USBSerial.printf("[power] awake; audio=%s\n",
                   maintenanceMute.muted() ? "maintenance-muted" :
                   (audioReady ? "ready" : "FAILED-muted"));
}

void idleStandby() {
  // Native USB Serial/JTAG is not guaranteed to survive light sleep. Keep the
  // CPU awake when a data host is attached so maintenance commands and the
  // verifier remain reliable; a charger-only cable still uses light sleep.
  if (usbDataConnected) {
    delay(20);
    return;
  }

  esp_err_t result = esp_sleep_enable_timer_wakeup(kStandbyPollUs);
  if (result == ESP_OK) result = esp_light_sleep_start();
  if (result != ESP_OK) {
    if (!standbySleepFailureReported) {
      standbySleepFailureReported = true;
      USBSerial.printf("[power] warning: light sleep failed: %s\n",
                       esp_err_to_name(result));
    }
    // Fail closed to the old low-risk polling behavior instead of spinning if
    // a board/library regression prevents light sleep.
    delay(20);
  }
}

void pollPowerButton(uint32_t now) {
  if (!powerButtonAvailable) return;
  if (!standbyMode && now - lastPowerPollMs < kAwakePowerPollMs) return;
  lastPowerPollMs = now;
  ++powerPollCount;
  const bool rawPressed = expander.digitalRead(kPowerButtonPin) == HIGH;
  if (rawPressed != powerRawPressed) {
    powerRawPressed = rawPressed;
    powerRawChangedAtMs = now;
    return;
  }
  if (now - powerRawChangedAtMs < kPowerDebounceMs) return;

  if (powerStablePressed != rawPressed) {
    powerStablePressed = rawPressed;
    if (powerStablePressed) {
      if (powerButtonArmed) {
        powerPressActive = true;
        powerPressedAtMs = now;
      }
    } else if (!powerButtonArmed) {
      // A PWR press may still be held while the PMIC cold-boots the ESP. Its
      // first debounced release only arms the control; it must not sleep again.
      powerButtonArmed = true;
      powerPressActive = false;
    } else if (powerPressActive) {
      powerPressActive = false;
      const uint32_t heldMs = now - powerPressedAtMs;
      if (heldMs < kSoftwareShortPressMaxMs) {
        setStandby(!standbyMode, now);
      } else {
        USBSerial.printf("[power] long release ignored at %u ms; PMIC owns hard-off\n",
                         static_cast<unsigned>(heldMs));
      }
    }
    return;
  }

  // Normal boots often begin with P4 already LOW, so arm only after that LOW
  // has itself survived the debounce interval.
  if (!powerStablePressed && !powerButtonArmed && !powerPressActive) {
    powerButtonArmed = true;
  }
}

bool replayHit(int32_t x, int32_t y) {
  const int32_t dx = x - kReplayCenterX;
  const int32_t dy = y - kReplayCenterY;
  return dx * dx + dy * dy <= kReplayHitRadius * kReplayHitRadius;
}

uint8_t chooseDiagnosticPalette(const CreatureSprite& sprite,
                                uint32_t random) {
  uint8_t eligibleCount = 0;
  for (uint8_t palette = 0; palette < kPaletteCount; ++palette) {
    if ((sprite.automaticPaletteMask & (1u << palette)) == 0) continue;
    if (palette == activeReward.paletteIndex) continue;
    ++eligibleCount;
  }
  const bool canAvoidRepeat = eligibleCount > 0;
  if (!canAvoidRepeat) {
    for (uint8_t palette = 0; palette < kPaletteCount; ++palette) {
      if (sprite.automaticPaletteMask & (1u << palette)) ++eligibleCount;
    }
  }
  if (eligibleCount == 0) return 0;  // Generated assets reject this condition.
  uint8_t draw = static_cast<uint8_t>((random >> 5) % eligibleCount);
  for (uint8_t palette = 0; palette < kPaletteCount; ++palette) {
    if ((sprite.automaticPaletteMask & (1u << palette)) == 0) continue;
    if (canAvoidRepeat && palette == activeReward.paletteIndex) continue;
    if (draw == 0) return palette;
    --draw;
  }
  return 0;
}

CreatureRewardPlan makeDiagnosticReward(bool rare,
                                        int16_t requestedCreature = -1) {
  const uint32_t random = esp_random();
  CreatureRewardPlan plan{};
  plan.creatureIndex = requestedCreature >= 0 &&
                               requestedCreature < kCreatureCount
                           ? static_cast<uint8_t>(requestedCreature)
                           : static_cast<uint8_t>(
                                 (activeReward.creatureIndex + 1 +
                                  random % (kCreatureCount - 1)) %
                                 kCreatureCount);
  const CreatureSprite& sprite = *kCreatures[plan.creatureIndex];
  plan.paletteIndex = chooseDiagnosticPalette(sprite, random);
  plan.patternStyle = rare ? 0 : static_cast<uint8_t>((random >> 11) % 4);
  plan.patternSeed = random ^ 0xA11CE55Du;
  plan.rare = rare;
  return plan;
}

void enterPreviewMode(uint32_t now) {
  if (!previewMode) game.suspend(now);
  previewMode = true;
}

void exitPreviewMode(uint32_t now) {
  previewMode = false;
  animatedRewardPreview = false;
  if (!standbyMode) game.resume(now);
}

void showHeldReward(bool rare, int16_t requestedCreature = -1) {
  activeReward = makeDiagnosticReward(rare, requestedCreature);
  enterPreviewMode(millis());
  animatedRewardPreview = false;
  // Use a point inside the full-water creature hold. This is the exact runtime
  // renderer, frozen for camera/display inspection until GAME.
  drawCreatureReward(
      1000, activeReward.creatureIndex, activeReward.paletteIndex,
      activeReward.patternStyle, activeReward.patternSeed, activeReward.rare);
  USBSerial.printf(
      "[test] held reward=%s palette=%s pattern=%u rare=%s "
      "treatment=%s; send GAME to resume\n",
      kCreatures[activeReward.creatureIndex]->id,
      kPaletteNames[activeReward.paletteIndex], activeReward.patternStyle,
      activeReward.rare ? "yes" : "no",
      activeReward.rare ?
          kCreatures[activeReward.creatureIndex]->rareTreatmentLabel :
          "none");
}

void showAnimatedReward(const CreatureRewardPlan& plan) {
  activeReward = plan;
  const uint32_t now = millis();
  enterPreviewMode(now);
  animatedRewardPreview = true;
  animatedRewardPreviewStartedAtMs = now;
  lastAnimatedRewardPreviewFrame = 0xffff;
  USBSerial.printf(
      "[test] animated reward=%s palette=%s pattern=%u seed=%lu rare=%s "
      "treatment=%s; "
      "send GAME to resume\n",
      kCreatures[activeReward.creatureIndex]->id,
      kPaletteNames[activeReward.paletteIndex],
      activeReward.patternStyle,
      static_cast<unsigned long>(activeReward.patternSeed),
      activeReward.rare ? "yes" : "no",
      activeReward.rare ?
          kCreatures[activeReward.creatureIndex]->rareTreatmentLabel :
          "none");
}

void showAnimatedReward(bool rare, uint8_t requestedCreature) {
  showAnimatedReward(makeDiagnosticReward(rare, requestedCreature));
}

void handlePreviewCommands() {
  if (!USBSerial.available()) return;
  String command = USBSerial.readStringUntil('\n');
  command.trim();
  if (command == "SLEEP") {
    setStandby(true, millis());
    return;
  }
  if (command == "WAKE") {
    setStandby(false, millis());
    return;
  }
  if (command == "MUTE" || command == "UNMUTE") {
    const bool requestedMute = command == "MUTE";
    const MaintenanceMuteEvent event = maintenanceMute.setMuted(requestedMute);
    handleMaintenanceMuteEvent(event, millis());
    USBSerial.printf("[mute] requested=%s state=%s usb_data=%s\n",
                     requestedMute ? "on" : "off",
                     maintenanceMute.muted() ? "on" : "off",
                     usbDataConnected ? "yes" : "no");
    return;
  }
  if (command == "STATUS") {
    reportBattery();
    const Round& round = game.round();
    const char* audioState = standbyMode ? "suspended" :
                             (maintenanceMute.muted() ? "muted" :
                             (AudioPlan::ready() ? "ready" : "FAILED"));
    USBSerial.printf(
        "[status] psram=%u audio=%s audio_power=%s audio_idle_downs=%u "
        "audio_write_failures=%u volume=%u imu=%s preview=%s standby=%s "
        "mute=%s usb_data=%s reward_clean=%u reward_pity=%u "
        "target=%c distractor=%c distinct=%s slide_left=%d,%d "
        "slide_right=%d,%d motion_rate=%u,%u touch_irq_gate=%s touch_polls=%u "
        "power_polls=%u\n",
        ESP.getPsramSize(), audioState, AudioPlan::powerState(),
        static_cast<unsigned>(AudioPlan::idlePowerDownCount()),
        static_cast<unsigned>(AudioPlan::writeFailureCount()),
        kAudioVolumePercent,
        imuAvailable ? "ready" : "FAILED", previewMode ? "yes" : "no",
        standbyMode ? "yes" : "no",
        maintenanceMute.muted() ? "on" : "off",
        usbDataConnected ? "yes" : "no", rewardSelector.cleanProgress(),
        rewardSelector.correctsSinceRare(), GameEngine::letter(round.target),
        GameEngine::letter(round.distractor),
        round.target != round.distractor ? "yes" : "NO",
        leftSlideX, leftSlideY, rightSlideX, rightSlideY,
        static_cast<unsigned>(leftMotionEase * 1000.0f),
        static_cast<unsigned>(rightMotionEase * 1000.0f),
        touchInterruptGateAvailable ? "yes" : "no",
        static_cast<unsigned>(touchPollCount),
        static_cast<unsigned>(powerPollCount));
    return;
  }
  if (standbyMode) {
    USBSerial.println("[power] asleep; send WAKE before other commands");
    return;
  }

  if (command == "FRAME") {
    maintenanceMute.cancelPending();
    const bool alreadyPreviewing = previewMode;
    enterPreviewMode(millis());
    animatedRewardPreview = false;
    constexpr size_t frameBytes = LCD_WIDTH * LCD_HEIGHT * sizeof(uint16_t);
    const size_t received = USBSerial.readBytes(
        reinterpret_cast<char*>(gfx->getFramebuffer()), frameBytes);
    if (received == frameBytes) {
      gfx->flush();
      USBSerial.println("[preview] frame displayed");
    } else {
      if (!alreadyPreviewing) exitPreviewMode(millis());
      USBSerial.printf("[preview] short frame: %u/%u\n",
                       static_cast<unsigned>(received),
                       static_cast<unsigned>(frameBytes));
    }
  } else if (command == "GAME") {
    maintenanceMute.cancelPending();
    exitPreviewMode(millis());
    drawRound();
    USBSerial.println("[preview] game resumed");
  } else if (command == "AUDIO" || command == "REPLAY") {
    if (!replayCurrentPrompt(millis())) {
      USBSerial.println("[replay] unavailable during celebration");
    }
  } else if (command == "ANIMATE") {
    maintenanceMute.cancelPending();
    exitPreviewMode(millis());
    dispatch(game.choose(game.round().targetOnLeft, millis()));
    USBSerial.println("[test] correct-choice animation triggered");
  } else if (command.startsWith("ANIMATE_VARIANT ")) {
    maintenanceMute.cancelPending();
    if (game.celebrating()) {
      USBSerial.println("[test] animated variant unavailable during celebration");
      return;
    }
    unsigned int creatureValue = 0;
    unsigned int paletteValue = 0;
    unsigned int patternValue = 0;
    unsigned int rareValue = 0;
    unsigned long seedValue = 0;
    char trailing = '\0';
    const int fields = sscanf(
        command.c_str(), "ANIMATE_VARIANT %u %u %u %u %lu %c",
        &creatureValue, &paletteValue, &patternValue, &rareValue, &seedValue,
        &trailing);
    if (fields != 5 || creatureValue >= kCreatureCount ||
        paletteValue >= kPaletteCount || patternValue >= kPatternCount ||
        rareValue > 1) {
      USBSerial.println(
          "[test] usage: ANIMATE_VARIANT creature(0..7) palette(0..5) "
          "pattern(0..3) rare(0|1) seed(uint32)");
      return;
    }
    const CreatureSprite& sprite = *kCreatures[creatureValue];
    if ((sprite.automaticPaletteMask & (1u << paletteValue)) == 0) {
      USBSerial.println("[test] palette is excluded for this production species");
      return;
    }
    if (rareValue != 0 && patternValue != 0) {
      USBSerial.println("[test] rare authored treatments require pattern 0");
      return;
    }
    CreatureRewardPlan plan{};
    plan.creatureIndex = static_cast<uint8_t>(creatureValue);
    plan.paletteIndex = static_cast<uint8_t>(paletteValue);
    plan.patternStyle = static_cast<uint8_t>(patternValue);
    plan.patternSeed = static_cast<uint32_t>(seedValue);
    plan.rare = rareValue != 0;
    showAnimatedReward(plan);
  } else if (command.startsWith("ANIMATE_CREATURE ") ||
             command.startsWith("ANIMATE_RARE_CREATURE ")) {
    maintenanceMute.cancelPending();
    if (game.celebrating()) {
      USBSerial.println("[test] animated reward unavailable during celebration");
      return;
    }
    const bool rare = command.startsWith("ANIMATE_RARE_CREATURE ");
    const String prefix = rare ? "ANIMATE_RARE_CREATURE " :
                                 "ANIMATE_CREATURE ";
    String value = command.substring(prefix.length());
    value.trim();
    bool valid = value.length() > 0;
    for (uint16_t index = 0; index < value.length(); ++index) {
      valid &= value[index] >= '0' && value[index] <= '9';
    }
    const long requestedValue = valid ? value.toInt() : -1;
    if (requestedValue < 0 || requestedValue >= kCreatureCount) {
      USBSerial.printf("[test] creature index must be 0..%u\n",
                       kCreatureCount - 1);
      return;
    }
    showAnimatedReward(rare, static_cast<uint8_t>(requestedValue));
  } else if (command.startsWith("HOLD_CREATURE ") ||
             command.startsWith("HOLD_RARE_CREATURE ")) {
    maintenanceMute.cancelPending();
    if (game.celebrating()) {
      USBSerial.println("[test] held reward unavailable during celebration");
      return;
    }
    const bool rare = command.startsWith("HOLD_RARE_CREATURE ");
    const String prefix = rare ? "HOLD_RARE_CREATURE " : "HOLD_CREATURE ";
    String value = command.substring(prefix.length());
    value.trim();
    bool valid = value.length() > 0;
    for (uint16_t index = 0; index < value.length(); ++index) {
      valid &= value[index] >= '0' && value[index] <= '9';
    }
    const long requestedValue = valid ? value.toInt() : -1;
    if (requestedValue < 0 || requestedValue >= kCreatureCount) {
      USBSerial.printf("[test] creature index must be 0..%u\n",
                       kCreatureCount - 1);
      return;
    }
    showHeldReward(rare, static_cast<int16_t>(requestedValue));
  } else if (command == "HOLD_REWARD" || command == "HOLD_RARE") {
    maintenanceMute.cancelPending();
    if (game.celebrating()) {
      USBSerial.println("[test] held reward unavailable during celebration");
      return;
    }
    showHeldReward(command == "HOLD_RARE");
  } else if (command == "REWARD" || command == "RARE") {
    maintenanceMute.cancelPending();
    exitPreviewMode(millis());
    if (game.celebrating()) {
      forcedRewardMode = ForcedRewardMode::none;
      USBSerial.println("[test] reward unavailable during celebration");
      return;
    }
    forcedRewardMode = command == "RARE" ? ForcedRewardMode::rare :
                                           ForcedRewardMode::common;
    dispatch(game.choose(game.round().targetOnLeft, millis()));
    USBSerial.printf("[test] %s reward triggered without rarity progress\n",
                     command == "RARE" ? "rare" : "common");
  } else if (command == "WRONG") {
    maintenanceMute.cancelPending();
    exitPreviewMode(millis());
    dispatch(game.choose(!game.round().targetOnLeft, millis()));
    USBSerial.println("[test] wrong-choice response triggered");
  } else if (command == "TILT" || command == "MOTION") {
    exitPreviewMode(millis());
    leftSlideX = leftSlideX >= 0 ? -kMaxTileSlideX : kMaxTileSlideX;
    leftSlideY = leftSlideY >= 0 ? kMaxTileSlideY : -kMaxTileSlideY;
    rightSlideX = leftSlideX;
    rightSlideY = leftSlideY;
    easedLeftSlideX = easedRightSlideX = leftSlideX;
    easedLeftSlideY = easedRightSlideY = leftSlideY;
    drawRound();
    USBSerial.printf("[test] slide frame=%d,%d\n", leftSlideX, leftSlideY);
  }
}

void dispatch(const Event& event) {
  const char target = GameEngine::letter(game.round().target);
  switch (event.type) {
    case EventType::roundStarted:
      randomizeMotionRates();
      USBSerial.printf("[round] target=%c distractor=%c side=%s layout=%u prompt=%u\n",
                       target, GameEngine::letter(game.round().distractor),
                       game.round().targetOnLeft ? "left" : "right",
                       game.round().layoutVariant, event.variant);
      drawRound();
      AudioPlan::initial(event.variant, target);
      break;
    case EventType::nudge:
      USBSerial.printf("[nudge] level=%u variant=%u target=%c\n",
                       game.nudgeLevel(), event.variant, target);
      AudioPlan::nudge(event.variant, target);
      break;
    case EventType::wrongChoice:
      maintenanceMute.cancelPending();
      rewardSelector.onWrong();
      USBSerial.printf("[choice] wrong variant=%u\n", event.variant);
      AudioPlan::wrong(event.variant);
      break;
    case EventType::correctChoice: {
      maintenanceMute.cancelPending();
      if (forcedRewardMode == ForcedRewardMode::none) {
        activeReward = rewardSelector.onCorrect();
      } else {
        activeReward = makeDiagnosticReward(
            forcedRewardMode == ForcedRewardMode::rare);
        forcedRewardMode = ForcedRewardMode::none;
      }
      const uint8_t bubbleVariant = rewardAudioSelector.nextBubble();
      USBSerial.printf(
          "[choice] correct variant=%u reward=%s palette=%s pattern=%u "
          "rare=%s treatment=%s praise=%s bubble=%s creature_sfx=%s "
          "reward_mix=%s clean=%u pity=%u\n",
          event.variant, kCreatures[activeReward.creatureIndex]->id,
          kPaletteNames[activeReward.paletteIndex], activeReward.patternStyle,
          activeReward.rare ? "yes" : "no",
          activeReward.rare ?
              kCreatures[activeReward.creatureIndex]->rareTreatmentLabel :
              "none",
          AudioPlan::rewardPraiseId(bubbleVariant,
                                    activeReward.creatureIndex),
          AudioPlan::bubbleSfxId(bubbleVariant),
          AudioPlan::creatureSfxId(activeReward.creatureIndex),
          AudioPlan::rewardMixId(bubbleVariant, activeReward.creatureIndex),
          rewardSelector.cleanProgress(), rewardSelector.correctsSinceRare());
      AudioPlan::celebrate(bubbleVariant, activeReward.creatureIndex);
      lastCelebrationFrame = 0xffff;
      drawRound(2);
      break;
    }
    case EventType::none:
      break;
  }
}

void initializeBoard() {
  Wire.begin(IIC_SDA, IIC_SCL);
  if (!expander.begin(0x20)) {
    USBSerial.println("[fatal] XCA9554 not found");
    while (true) delay(1000);
  }
  for (uint8_t pin = 0; pin < 3; ++pin) {
    expander.pinMode(pin, OUTPUT);
    expander.digitalWrite(pin, LOW);
  }
  powerButtonAvailable = expander.pinMode(kPowerButtonPin, INPUT);
  if (!powerButtonAvailable) {
    USBSerial.println("[power] PWR input unavailable; standby disabled");
  }
  delay(20);
  for (uint8_t pin = 0; pin < 3; ++pin) expander.digitalWrite(pin, HIGH);
  if (powerButtonAvailable) {
    powerRawPressed = expander.digitalRead(kPowerButtonPin) == HIGH;
    powerStablePressed = powerRawPressed;
    powerRawChangedAtMs = millis();
    USBSerial.println("[power] PWR short-release standby enabled; long hold belongs to PMIC");
  }

  while (!touch->begin()) {
    USBSerial.println("[wait] CST820 touch controller");
    delay(500);
  }
  touchInterruptGateAvailable = touch->IIC_Write_Device_State(
      touch->Arduino_IIC_Touch::Device::TOUCH_DEVICE_INTERRUPT_MODE,
      touch->Arduino_IIC_Touch::Device_Mode::TOUCH_DEVICE_INTERRUPT_PERIODIC);
  if (!touchInterruptGateAvailable) {
    USBSerial.println(
        "[power] touch IRQ gate unavailable; retaining continuous polling");
  }
  touchInterruptPending = false;

  if (qmi.begin(Wire, QMI8658_L_SLAVE_ADDRESS, IIC_SDA, IIC_SCL)) {
    qmi.configAccelerometer(SensorQMI8658::ACC_RANGE_4G,
                            SensorQMI8658::ACC_ODR_62_5Hz,
                            SensorQMI8658::LPF_MODE_0);
    qmi.enableAccelerometer();
    imuAvailable = true;
    USBSerial.println("[imu] slow tile sliding enabled");
  } else {
    USBSerial.println("[imu] unavailable; static visuals");
  }

  if (!panel->begin()) {
    USBSerial.println("[fatal] CO5300 display initialization failed");
    while (true) delay(1000);
  }
  panel->setBrightness(kDisplayBrightness);
  if (!gfx->begin(GFX_SKIP_OUTPUT_BEGIN)) {
    USBSerial.println("[fatal] off-screen framebuffer allocation failed");
    while (true) delay(1000);
  }
  USBSerial.printf("[display] buffered; psram=%u bytes\n", ESP.getPsramSize());
}

void setup() {
  USBSerial.begin(115200);
  USBSerial.setTxTimeoutMs(0);
  USBSerial.setTimeout(8000);
  initializeBoard();
  sampleBattery(millis());
  maintenanceMute.update(millis(), USBSerial.isPlugged());
  usbDataConnected = maintenanceMute.dataConnected();
  const bool audioReady = AudioPlan::begin();
  game = GameEngine(esp_random());
  rewardSelector.reset(esp_random());
  rewardAudioSelector.reset(esp_random());
  if (AudioPlan::enabled()) {
    USBSerial.printf("[boot] phonics game; audio=%s volume=%u\n",
                     audioReady ? "ready" : "FAILED", kAudioVolumePercent);
  } else {
    USBSerial.println("[boot] phonics game; audio=MUTED");
  }
  dispatch(game.begin(millis()));
}

void loop() {
  const uint32_t loopNow = millis();
  pollPowerButton(loopNow);
  pollMaintenanceMute(loopNow);
  AudioPlan::service(loopNow);
  handlePreviewCommands();
  if (standbyMode) {
    idleStandby();
    return;
  }
  if (previewMode) {
    if (animatedRewardPreview) {
      // Re-sample after command handling: showAnimatedReward() records its
      // start time there, so reusing loopNow from before the command could
      // unsigned-underflow and flash an arbitrary first frame.
      const uint32_t previewNow = millis();
      const uint32_t previewElapsed =
          previewNow - animatedRewardPreviewStartedAtMs;
      const uint32_t renderElapsed = kWaterRiseEndMs + previewElapsed;
      const uint16_t previewFrame = static_cast<uint16_t>(
          (previewElapsed / 55) % (kFrameCount * 2));
      if (previewFrame != lastAnimatedRewardPreviewFrame) {
        lastAnimatedRewardPreviewFrame = previewFrame;
        // Pin the surface to the exact full-water production state while the
        // effects clock advances continuously. Creature frames still repeat
        // every 4 * 110 ms, but water, bubbles, and sparkles never snap back.
        drawCreatureReward(kWaterRiseEndMs, activeReward.creatureIndex,
                           activeReward.paletteIndex,
                           activeReward.patternStyle,
                           activeReward.patternSeed, activeReward.rare,
                           renderElapsed);
      }
    }
    delay(8);
    return;
  }
  const uint32_t now = millis();
  if (now - lastBatterySampleMs >= kBatterySampleMs) sampleBattery(now);
  dispatch(game.update(now));

  if (game.celebrating()) {
    const uint32_t elapsed = game.celebrationElapsed(now);
    uint16_t frame;
    if (elapsed < kCorrectPulseEndMs) {
      frame = elapsed < 180 ? 0 : (elapsed < 360 ? 1 : 2);
    } else if (elapsed < kWaterRiseEndMs) {
      frame = 10 + static_cast<uint16_t>(
          (elapsed - kCorrectPulseEndMs) / 40);
    } else if (elapsed < kCreatureRewardEndMs) {
      frame = 32 + static_cast<uint16_t>(
          (elapsed - kWaterRiseEndMs) / 100);
    } else if (elapsed < kWaterRecedeEndMs) {
      frame = 64 + static_cast<uint16_t>(
          (elapsed - kCreatureRewardEndMs) / 40);
    } else {
      // One latched terminal frame gives the compositor a reliable 120 ms
      // black beat without repeatedly drawing water only to clip it away.
      frame = 0xfffe;
    }
    if (frame != lastCelebrationFrame) {
      lastCelebrationFrame = frame;
      if (elapsed < kCorrectPulseEndMs) {
        drawRound(frame == 0 ? 2 : (frame == 1 ? 6 : 0));
      } else if (elapsed >= kWaterRecedeEndMs) {
        drawBackground();
        gfx->flush();
      } else {
        drawCreatureReward(elapsed, activeReward.creatureIndex,
                           activeReward.paletteIndex,
                           activeReward.patternStyle,
                           activeReward.patternSeed, activeReward.rare);
      }
    }
  } else if (!game.celebrating()) {
    const bool motionChanged = updateMotion(now);
    if (motionChanged || batteryVisualDirty) drawRound();
  }

  // TP_INT gates the idle path. Once a press begins, retain the established
  // 8 ms polling cadence through release so hit testing and USB-only double
  // tap timing are unchanged.
  const bool touchSafetyPollDue =
      now - lastTouchSafetyPollMs >= kTouchSafetyPollMs;
  if (!touchInterruptGateAvailable || touchInterruptPending || touchWasDown ||
      awaitingTouchRelease || touchSafetyPollDue) {
    touchInterruptPending = false;
    lastTouchSafetyPollMs = now;
    ++touchPollCount;
    const int32_t touchPoints = touch->IIC_Read_Device_Value(
        touch->Arduino_IIC_Touch::Value_Information::TOUCH_FINGER_NUMBER);
    const bool touchDown = touchPoints > 0;
    if (awaitingTouchRelease) {
      touchWasDown = touchDown;
      if (!touchDown) {
        awaitingTouchRelease = false;
        touchWasDown = false;
      }
    } else if (touchDown && !touchWasDown && !game.celebrating()) {
      const int32_t x = touch->IIC_Read_Device_Value(
          touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_X);
      const int32_t y = touch->IIC_Read_Device_Value(
          touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_Y);
      const CardRect left = cardRect(true, game.round().layoutVariant);
      const CardRect right = cardRect(false, game.round().layoutVariant);
      const auto contains = [](const CardRect& card, int32_t px, int32_t py) {
        return px >= card.x && px < card.x + card.w &&
               py >= card.y && py < card.y + card.h;
      };
      if (replayHit(x, y)) {
        // The complete replay hit target participates in the maintenance
        // double tap. Restricting this to the smaller painted circle made
        // ordinary edge taps replay immediately and cancel an otherwise
        // natural second tap.
        const MaintenanceMuteEvent event = usbDataConnected ?
            maintenanceMute.innerReplayTap(now) :
            maintenanceMute.outerReplayTap();
        handleMaintenanceMuteEvent(event, now);
      } else if (contains(left, x, y)) {
        maintenanceMute.cancelPending();
        dispatch(game.choose(true, now));
      } else if (contains(right, x, y)) {
        maintenanceMute.cancelPending();
        dispatch(game.choose(false, now));
      }
      touchWasDown = touchDown;
    } else {
      touchWasDown = touchDown;
    }
  }
  delay(8);
}
