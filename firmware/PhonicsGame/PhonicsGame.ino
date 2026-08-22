#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_XCA9554.h>
#include "Arduino_DriveBus_Library.h"
#include "Arduino_GFX_Library.h"
#include "HWCDC.h"
#include "SensorQMI8658.hpp"
#include "pin_config.h"
#include "esp_random.h"

#include "AudioPlan.h"
#include "GameEngine.h"
#include "LayoutGeometry.h"
#include "fonts/NunitoBlack112.h"

using namespace phonics_game;

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

constexpr uint16_t kMoonlight = 0xEF5C;
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint8_t kDisplayBrightness = 190;
constexpr uint8_t kPowerButtonPin = 4;
constexpr uint32_t kPowerDebounceMs = 50;
constexpr uint32_t kSoftwareShortPressMaxMs = 1500;
constexpr uint32_t kMotionSampleMs = 80;
// Permanent a-z identities. Never randomize or reorder this table: the color
// is part of the child's visual memory of each letter.
constexpr uint16_t kLetterColors[26] = {
    0x934A, 0x1B6A, 0x63C8, 0x93A3, 0x2B4A, 0x8B4A, 0x13A9,
    0x8364, 0x3B88, 0x9345, 0x238B, 0x7323, 0x538A, 0x9325,
    0x1387, 0x6B68, 0x7B23, 0x2B8B, 0x9328, 0x1B85, 0x8B66,
    0x43AA, 0x9323, 0x138A, 0x7B46, 0x6B43,
};

bool touchWasDown = false;
uint8_t lastCelebrationFrame = 0xff;
uint32_t lastMotionSampleMs = 0;
float neutralAccelX = 0.0f;
float neutralAccelY = 0.0f;
float filteredAccelX = 0.0f;
float filteredAccelY = 0.0f;
float easedSlideX = 0.0f;
float easedSlideY = 0.0f;
bool motionReady = false;
bool imuAvailable = false;
int16_t tileSlideX = 0;
int16_t tileSlideY = 0;
bool previewMode = false;
bool standbyMode = false;
bool powerButtonAvailable = false;
bool awaitingTouchRelease = false;
bool powerRawPressed = false;
bool powerStablePressed = false;
bool powerButtonArmed = false;
bool powerPressActive = false;
uint32_t powerRawChangedAtMs = 0;
uint32_t powerPressedAtMs = 0;

void onTouchInterrupt() {
  touch->IIC_Interrupt_Flag = true;
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

CardRect cardRect(bool left, uint8_t layoutVariant, int16_t pulse = 0) {
  return makeCardRect(left, layoutVariant, tileSlideX, tileSlideY, pulse);
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

void drawLetterTexture(const CardRect& card, char letter, uint16_t baseColor) {
  // The seed and motif depend only on the letter, so the visual anchor is
  // identical in every round and across restarts.
  uint32_t state = 0x9E3779B9u ^
                   (static_cast<uint32_t>(letter - 'a' + 1) * 0x45D9F3Bu);
  const uint16_t texture = blend565(kWhite, baseColor, 34);
  for (uint8_t i = 0; i < 13; ++i) {
    state = state * 1664525u + 1013904223u;
    const int16_t x = card.x + 17 +
                      static_cast<int16_t>((state >> 8) % (card.w - 34));
    state = state * 1664525u + 1013904223u;
    const int16_t y = card.y + 18 +
                      static_cast<int16_t>((state >> 8) % (card.h - 36));
    switch ((letter - 'a') % 4) {
      case 0:
        gfx->fillCircle(x, y, 2 + (i % 2), texture);
        break;
      case 1:
        gfx->drawLine(x - 4, y + 3, x + 4, y - 3, texture);
        break;
      case 2:
        gfx->drawLine(x - 3, y, x + 3, y, texture);
        gfx->drawLine(x, y - 3, x, y + 3, texture);
        break;
      default:
        gfx->drawRect(x - 2, y - 2, 5, 5, texture);
        break;
    }
  }
}

void drawCard(const CardRect& card, char letter, bool pulsing) {
  const uint16_t color = kLetterColors[letter - 'a'];
  gfx->fillRoundRect(card.x + 3, card.y + 6, card.w, card.h, 20, 0x0204);
  gfx->fillRoundRect(card.x, card.y, card.w, card.h, 20,
                     blend565(color, 0x0000, pulsing ? 225 : 205));
  gfx->drawRoundRect(card.x, card.y, card.w, card.h, 20,
                     pulsing ? kWhite : blend565(kWhite, color, 145));
  gfx->drawFastHLine(card.x + 22, card.y + 11, card.w - 44,
                     blend565(kWhite, color, 165));
  drawLetterTexture(card, letter, color);

  char label[] = {letter, '\0'};
  // Four-pass dark halo preserves the silhouette without burdening motion redraws.
  constexpr int8_t halo[][2] = {{-2, 0}, {2, 0}, {0, -2}, {0, 2}};
  for (const auto& offset : halo) {
    drawCentered(label, card.x + card.w / 2 + offset[0],
                 card.y + card.h / 2 + offset[1], &NunitoBlack112,
                 blend565(0x0000, color, 165));
  }
  drawCentered(label, card.x + card.w / 2, card.y + card.h / 2,
               &NunitoBlack112, kWhite);
}

void drawReplayButton() {
  gfx->fillCircle(kReplayCenterX, kReplayCenterY, kReplayVisualRadius,
                  blend565(0x1CBF, 0x0000, 105));
  gfx->drawCircle(kReplayCenterX, kReplayCenterY, kReplayVisualRadius,
                  kMoonlight);
  gfx->drawCircle(kReplayCenterX, kReplayCenterY,
                  kReplayVisualRadius - 1, blend565(kWhite, 0x1CBF, 165));
  gfx->fillTriangle(kReplayCenterX - 8, kReplayCenterY - 11,
                    kReplayCenterX - 8, kReplayCenterY + 11,
                    kReplayCenterX + 11, kReplayCenterY, kWhite);
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

  // Low-pass the sensor and then ease the shared tile translation toward the
  // gravity target. A shared vector makes the pair feel loose while preserving
  // the proven gap between the cards at every frame.
  filteredAccelX = filteredAccelX * 0.88f + acceleration.x * 0.12f;
  filteredAccelY = filteredAccelY * 0.88f + acceleration.y * 0.12f;
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
  easedSlideX = easedSlideX * 0.92f + targetX * 0.08f;
  easedSlideY = easedSlideY * 0.92f + targetY * 0.08f;
  const int16_t nextX = constrain(static_cast<int>(roundf(easedSlideX)),
                                  -kMaxTileSlideX, kMaxTileSlideX);
  const int16_t nextY = constrain(static_cast<int>(roundf(easedSlideY)),
                                  -kMaxTileSlideY, kMaxTileSlideY);
  if (nextX == tileSlideX && nextY == tileSlideY) return false;
  tileSlideX = nextX;
  tileSlideY = nextY;
  return true;
}

void drawRound(int16_t correctPulse = 0) {
  drawBackground();
  drawReplayButton();
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

void setStandby(bool enabled, uint32_t now) {
  if (enabled == standbyMode) return;
  if (enabled) {
    standbyMode = true;
    game.suspend(now);
    const bool audioQuiet = AudioPlan::suspend();
    panel->setBrightness(0);
    panel->displayOff();
    touchWasDown = false;
    USBSerial.printf("[power] standby; audio=%s\n",
                     audioQuiet ? "quiet" : "muted-with-warning");
    return;
  }

  panel->setBrightness(0);
  panel->displayOn();
  gfx->flush();
  const bool audioReady = AudioPlan::resume();
  panel->setBrightness(kDisplayBrightness);
  game.resume(millis());
  standbyMode = false;
  awaitingTouchRelease = true;
  touchWasDown = true;
  USBSerial.printf("[power] awake; audio=%s\n",
                   audioReady ? "ready" : "FAILED-muted");
}

void pollPowerButton(uint32_t now) {
  if (!powerButtonAvailable) return;
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
  if (command == "STATUS") {
    const Round& round = game.round();
    const char* audioState = standbyMode ? "suspended" :
                             (AudioPlan::ready() ? "ready" : "FAILED");
    USBSerial.printf(
        "[status] psram=%u audio=%s volume=%u imu=%s preview=%s standby=%s "
        "target=%c distractor=%c distinct=%s slide=%d,%d\n",
        ESP.getPsramSize(), audioState, kAudioVolumePercent,
        imuAvailable ? "ready" : "FAILED", previewMode ? "yes" : "no",
        standbyMode ? "yes" : "no", GameEngine::letter(round.target),
        GameEngine::letter(round.distractor),
        round.target != round.distractor ? "yes" : "NO",
        tileSlideX, tileSlideY);
    return;
  }
  if (standbyMode) {
    USBSerial.println("[power] asleep; send WAKE before other commands");
    return;
  }

  if (command == "FRAME") {
    constexpr size_t frameBytes = LCD_WIDTH * LCD_HEIGHT * sizeof(uint16_t);
    const size_t received = USBSerial.readBytes(
        reinterpret_cast<char*>(gfx->getFramebuffer()), frameBytes);
    if (received == frameBytes) {
      previewMode = true;
      gfx->flush();
      USBSerial.println("[preview] frame displayed");
    } else {
      USBSerial.printf("[preview] short frame: %u/%u\n",
                       static_cast<unsigned>(received),
                       static_cast<unsigned>(frameBytes));
    }
  } else if (command == "GAME") {
    previewMode = false;
    drawRound();
    USBSerial.println("[preview] game resumed");
  } else if (command == "AUDIO" || command == "REPLAY") {
    if (!replayCurrentPrompt(millis())) {
      USBSerial.println("[replay] unavailable during celebration");
    }
  } else if (command == "ANIMATE") {
    previewMode = false;
    dispatch(game.choose(game.round().targetOnLeft, millis()));
    USBSerial.println("[test] correct-choice animation triggered");
  } else if (command == "WRONG") {
    previewMode = false;
    dispatch(game.choose(!game.round().targetOnLeft, millis()));
    USBSerial.println("[test] wrong-choice response triggered");
  } else if (command == "TILT" || command == "MOTION") {
    previewMode = false;
    tileSlideX = tileSlideX >= 0 ? -kMaxTileSlideX : kMaxTileSlideX;
    tileSlideY = tileSlideY >= 0 ? kMaxTileSlideY : -kMaxTileSlideY;
    easedSlideX = tileSlideX;
    easedSlideY = tileSlideY;
    drawRound();
    USBSerial.printf("[test] slide frame=%d,%d\n", tileSlideX, tileSlideY);
  }
}

void dispatch(const Event& event) {
  const char target = GameEngine::letter(game.round().target);
  switch (event.type) {
    case EventType::roundStarted:
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
      USBSerial.printf("[choice] wrong variant=%u\n", event.variant);
      AudioPlan::wrong(event.variant);
      break;
    case EventType::correctChoice:
      USBSerial.printf("[choice] correct variant=%u\n", event.variant);
      AudioPlan::praise(event.variant);
      lastCelebrationFrame = 0;
      drawRound(2);
      break;
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
  touch->IIC_Write_Device_State(
      touch->Arduino_IIC_Touch::Device::TOUCH_DEVICE_INTERRUPT_MODE,
      touch->Arduino_IIC_Touch::Device_Mode::TOUCH_DEVICE_INTERRUPT_PERIODIC);

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
  const bool audioReady = AudioPlan::begin();
  game = GameEngine(esp_random());
  if (AudioPlan::enabled()) {
    USBSerial.printf("[boot] phonics game; audio=%s volume=%u\n",
                     audioReady ? "ready" : "FAILED", kAudioVolumePercent);
  } else {
    USBSerial.println("[boot] phonics game; audio=MUTED");
  }
  dispatch(game.begin(millis()));
}

void loop() {
  pollPowerButton(millis());
  handlePreviewCommands();
  if (standbyMode) {
    delay(20);
    return;
  }
  if (previewMode) {
    delay(8);
    return;
  }
  const uint32_t now = millis();
  dispatch(game.update(now));

  if (game.celebrating()) {
    const uint32_t elapsed = game.celebrationElapsed(now);
    const uint8_t frame = elapsed < 180 ? 0 : (elapsed < 360 ? 1 : 2);
    if (frame != lastCelebrationFrame) {
      lastCelebrationFrame = frame;
      drawRound(frame == 1 ? 6 : 0);
    }
  } else if (!game.celebrating() && updateMotion(now)) {
    drawRound();
  }

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
      return px >= card.x && px < card.x + card.w && py >= card.y && py < card.y + card.h;
    };
    if (replayHit(x, y)) replayCurrentPrompt(now);
    else if (contains(left, x, y)) dispatch(game.choose(true, now));
    else if (contains(right, x, y)) dispatch(game.choose(false, now));
    touchWasDown = touchDown;
  } else {
    touchWasDown = touchDown;
  }
  delay(8);
}
