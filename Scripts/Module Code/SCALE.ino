#include <HX711.h>

#define LOADCELL_DOUT_PIN 4
#define LOADCELL_SCK_PIN  5

HX711 scale;

const float CALIBRATION_FACTOR = 0;
const long OFFSET = 0;

void setup() {
  
  Serial.begin(115200);

  scale.begin(LOADCELL_DOUT_PIN, LOADCELL_SCK_PIN);

  scale.set_scale(CALIBRATION_FACTOR);

  scale.set_offset(OFFSET);

  Serial.println("Load cell ready.");
}

void loop() {
  if (scale.is_ready()) {
    float weight = scale.get_units(10);

    Serial.print("WEIGHT : ");
    Serial.println(weight, 2);
  } else {
    Serial.println("HX711 not found!");
  }

  delay(200);
}
