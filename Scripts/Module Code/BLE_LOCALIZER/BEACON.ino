#include <BLEDevice.h>
#include <BLEScan.h>

BLEScan* pBLEScan;

class MyAdvertisedDeviceCallbacks: public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) {

    if (advertisedDevice.getName() == "CARRIER_BEACON") {

      int rssi = advertisedDevice.getRSSI();

      Serial.print("RSSI:");
      Serial.println(rssi);
    }
  }
};

void setup() {
  Serial.begin(115200);

  BLEDevice::init("");

  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setActiveScan(true);
}

void loop() {
  pBLEScan->start(1, false);
}