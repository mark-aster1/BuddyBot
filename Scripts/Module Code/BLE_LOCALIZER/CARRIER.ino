#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>

void setup() {
  BLEDevice::init("CARRIER_BEACON");

  BLEServer *pServer = BLEDevice::createServer();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();

  pAdvertising->start();
}

void loop() {
  delay(50);
}
