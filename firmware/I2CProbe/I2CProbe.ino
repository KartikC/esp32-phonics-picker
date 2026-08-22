#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_XCA9554.h>
#include "HWCDC.h"
#include "pin_config.h"

HWCDC USBSerial;
Adafruit_XCA9554 expander;

void setup() {
  USBSerial.begin(115200);
  USBSerial.setTxTimeoutMs(0);
  Wire.begin(IIC_SDA, IIC_SCL);
  USBSerial.println("[probe] I2C scan starting; audio hardware untouched");
  if (expander.begin(0x20)) {
    USBSerial.println("[probe] expander=0x20");
    for (uint8_t pin = 0; pin < 3; ++pin) {
      expander.pinMode(pin, OUTPUT);
      expander.digitalWrite(pin, LOW);
    }
    delay(20);
    for (uint8_t pin = 0; pin < 3; ++pin) expander.digitalWrite(pin, HIGH);
  } else {
    USBSerial.println("[probe] expander not found at 0x20");
  }
}
void loop() {
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      USBSerial.printf("[probe] address=0x%02X\n", address);
      ++found;
    }
  }
  USBSerial.printf("[probe] found=%u\n", found);
  delay(3000);
}
