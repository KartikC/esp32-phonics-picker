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
#include "fonts/NunitoBlack112.h"
#include "fonts/NunitoBold28.h"

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

struct CardRect {
  int16_t x;
  int16_t y;
  int16_t w;
  int16_t h;
};

struct LayoutOffset {
  int8_t leftX;
  int8_t leftY;
  int8_t rightX;
  int8_t rightY;
};

constexpr LayoutOffset kLayoutOffsets[kLayoutVariantCount] = {
    {0, 0, 0, 6}, {-7, 7, 5, -2}, {5, -4, -7, 7},
    {-3, -6, 7, 3}, {7, 4, -4, -5}, {-5, 2, 4, 8},
};

constexpr uint16_t kBackgroundTop = 0x0863;    // #050D1C, RGB565
constexpr uint16_t kBackgroundBottom = 0x1108; // #121F3E, RGB565
constexpr uint16_t kMoonlight = 0xEF5C;
constexpr uint16_t kWhite = 0xFFFF;
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
float smoothAccelX = 0.0f;
float smoothAccelY = 0.0f;
bool motionReady = false;
bool imuAvailable = false;
int8_t visualTiltX = 0;
int8_t visualTiltY = 0;
bool previewMode = false;

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
  const LayoutOffset& offset = kLayoutOffsets[layoutVariant];
  const int16_t baseX = left ? 22 : 201;
  const int16_t xOffset = left ? offset.leftX : offset.rightX;
  const int16_t yOffset = left ? offset.leftY : offset.rightY;
  return CardRect{static_cast<int16_t>(baseX + xOffset + visualTiltX - pulse),
                  static_cast<int16_t>(220 + yOffset + visualTiltY - pulse),
                  static_cast<int16_t>(145 + pulse * 2),
                  static_cast<int16_t>(158 + pulse * 2)};
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
                     blend565(color, kBackgroundBottom, pulsing ? 225 : 205));
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

void drawPromptHeader() {
  const int16_t x = LCD_WIDTH / 2 + visualTiltX;
  drawCentered("listen", x, 87 + visualTiltY, &NunitoBold28, kMoonlight);
  gfx->drawCircle(x, 139 + visualTiltY, 30, kMoonlight);
  gfx->fillTriangle(x - 10, 130 + visualTiltY,
                    x - 10, 148 + visualTiltY,
                    x + 10, 139 + visualTiltY, kMoonlight);
  drawCentered("pick one", x, 190 + visualTiltY, &NunitoBold28, kMoonlight);
}

bool updateMotion(uint32_t now) {
  if (!imuAvailable || now - lastMotionSampleMs < 100 || !qmi.getDataReady()) return false;
  lastMotionSampleMs = now;
  IMUdata acceleration;
  if (!qmi.getAccelerometer(acceleration.x, acceleration.y, acceleration.z)) {
    return false;
  }
  if (!motionReady) {
    neutralAccelX = smoothAccelX = acceleration.x;
    neutralAccelY = smoothAccelY = acceleration.y;
    motionReady = true;
    return false;
  }
  // Heavy smoothing and a seven-pixel cap make motion visible but calm.
  smoothAccelX = smoothAccelX * 0.82f + acceleration.x * 0.18f;
  smoothAccelY = smoothAccelY * 0.82f + acceleration.y * 0.18f;
  const int8_t nextX = constrain(static_cast<int>(roundf((smoothAccelX - neutralAccelX) * 9.0f)), -7, 7);
  const int8_t nextY = constrain(static_cast<int>(roundf((smoothAccelY - neutralAccelY) * 9.0f)), -7, 7);
  if (nextX == visualTiltX && nextY == visualTiltY) return false;
  visualTiltX = nextX;
  visualTiltY = nextY;
  return true;
}

void drawRound(int16_t correctPulse = 0) {
  drawBackground();
  drawPromptHeader();
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

void handlePreviewCommands() {
  if (!USBSerial.available()) return;
  String command = USBSerial.readStringUntil('\n');
  command.trim();
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
  } else if (command == "STATUS") {
    const Round& round = game.round();
    USBSerial.printf(
        "[status] psram=%u audio=%s volume=%u imu=%s preview=%s "
        "target=%c distractor=%c distinct=%s tilt=%d,%d\n",
        ESP.getPsramSize(), AudioPlan::ready() ? "ready" : "FAILED",
        kAudioVolumePercent,
        imuAvailable ? "ready" : "FAILED", previewMode ? "yes" : "no",
        GameEngine::letter(round.target), GameEngine::letter(round.distractor),
        round.target != round.distractor ? "yes" : "NO",
        visualTiltX, visualTiltY);
  } else if (command == "AUDIO") {
    const Round& round = game.round();
    AudioPlan::initial(round.promptVariant, GameEngine::letter(round.target));
    USBSerial.printf("[test] replayed prompt=%u target=%c volume=%u\n",
                     round.promptVariant, GameEngine::letter(round.target),
                     kAudioVolumePercent);
  } else if (command == "ANIMATE") {
    previewMode = false;
    dispatch(game.choose(game.round().targetOnLeft, millis()));
    USBSerial.println("[test] correct-choice animation triggered");
  } else if (command == "WRONG") {
    previewMode = false;
    dispatch(game.choose(!game.round().targetOnLeft, millis()));
    USBSerial.println("[test] wrong-choice response triggered");
  } else if (command == "TILT") {
    previewMode = false;
    visualTiltX = visualTiltX >= 0 ? -7 : 7;
    visualTiltY = visualTiltY >= 0 ? 5 : -5;
    drawRound();
    USBSerial.printf("[test] tilt frame=%d,%d\n", visualTiltX, visualTiltY);
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
  delay(20);
  for (uint8_t pin = 0; pin < 3; ++pin) expander.digitalWrite(pin, HIGH);

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
    USBSerial.println("[imu] subtle visual tilt enabled");
  } else {
    USBSerial.println("[imu] unavailable; static visuals");
  }

  if (!panel->begin()) {
    USBSerial.println("[fatal] CO5300 display initialization failed");
    while (true) delay(1000);
  }
  panel->setBrightness(190);
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
  handlePreviewCommands();
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
  if (touchDown && !touchWasDown && !game.celebrating()) {
    const int32_t x = touch->IIC_Read_Device_Value(
        touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_X);
    const int32_t y = touch->IIC_Read_Device_Value(
        touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_Y);
    const CardRect left = cardRect(true, game.round().layoutVariant);
    const CardRect right = cardRect(false, game.round().layoutVariant);
    const auto contains = [](const CardRect& card, int32_t px, int32_t py) {
      return px >= card.x && px < card.x + card.w && py >= card.y && py < card.y + card.h;
    };
    if (contains(left, x, y)) dispatch(game.choose(true, now));
    else if (contains(right, x, y)) dispatch(game.choose(false, now));
  }
  touchWasDown = touchDown;
  delay(8);
}
