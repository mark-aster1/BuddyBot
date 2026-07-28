#include <ESP32Servo.h>
#include <math.h>

Servo base, firstLeg, secondLeg, thirdLeg, clawAngle, claw;
int positions[6]   = {1500, 1100, 2500, 1470, 1530, 1450};
int straightPos[6] = {1500, 1450, 1500, 1550, 1530, 1450};
int zeroPos[6]     = {1500, 1100, 2500, 1470, 1530, 1450};
int dancePosA[6]   = {1300, 1300, 1900, 1300, 1530, 1450};
int dancePosB[6]   = {1700, 1300, 1900, 1300, 1530, 1450};
int yesPos[6]      = {1500, 1450, 1500, 1300, 1530, 1450};
int grabPos[6]     = {1500, 1450, 1500, 1100, 1530, 1450};
int throwPos[6]    = {1300, 1450, 1500, 1600, 1530, 2050};

const float L2 = 150.0;
const float L3 = 150.0;
const float L4 = 81.8;
const float TOOL_OFFSET = 28.55;
const float CLAW_LEN = 185.0;
const float BASE_HEIGHT = 72.0;
const float US_PER_DEG = 2000.0 / 180.0;

const float WAIST_ANCHOR_DEG = 180.0,  WAIST_ANCHOR_US = 1500;
const float SHOULDER_ANCHOR_DEG = 90.0, SHOULDER_ANCHOR_US = 1450;
const float ELBOW_ANCHOR_DEG = 0.0,    ELBOW_ANCHOR_US = 1500;
const float WRISTPITCH_ANCHOR_DEG = 0.0, WRISTPITCH_ANCHOR_US = 1550;
const float WRISTROLL_ANCHOR_DEG = 0.0,  WRISTROLL_ANCHOR_US = 1530;

bool INVERT_WAIST = false;
bool INVERT_SHOULDER = false;
bool INVERT_ELBOW = false;
bool INVERT_WRISTPITCH = false;
bool INVERT_WRISTROLL = false;

int JOINT_US_MIN[5] = {500, 500, 500, 500, 500};
int JOINT_US_MAX[5] = {2500, 2500, 2500, 2500, 2500};

int angleToUs(float angleDeg, float anchorDeg, float anchorUs, bool invert, int jointIndex) {
  float delta = angleDeg - anchorDeg;
  if (invert) delta = -delta;
  int us = (int)round(anchorUs + delta * US_PER_DEG);
  us = constrain(us, JOINT_US_MIN[jointIndex], JOINT_US_MAX[jointIndex]);
  return us;
}

bool solveBranch(float r, float h, float thetaTotalDeg, float rollDeg,
                  float &t2, float &t3, float &t4) {
  float thetaTotal = radians(thetaTotalDeg);
  float roll = radians(rollDeg);

  float fwdLen = CLAW_LEN * cos(roll);
  float toolR = TOOL_OFFSET * cos(thetaTotal + HALF_PI) + fwdLen * cos(thetaTotal);
  float toolH = TOOL_OFFSET * sin(thetaTotal + HALF_PI) + fwdLen * sin(thetaTotal);

  float p4r = r - toolR;
  float p4h = h - toolH;

  float p3r = p4r - L4 * cos(thetaTotal);
  float p3h = p4h - L4 * sin(thetaTotal);

  float dr = p3r - 0.0;
  float dh = p3h - BASE_HEIGHT;
  float D = sqrt(dr * dr + dh * dh);

  if (D > (L2 + L3) || D < fabs(L2 - L3)) return false;
  if (D < 1.0) D = 1.0;

  float alpha = atan2(dh, dr);
  float cosBeta = (L2 * L2 + D * D - L3 * L3) / (2 * L2 * D);
  cosBeta = constrain(cosBeta, -1.0, 1.0);
  float beta = acos(cosBeta);

  float t2rad = alpha + beta;

  float cosGamma = (L2 * L2 + L3 * L3 - D * D) / (2 * L2 * L3);
  cosGamma = constrain(cosGamma, -1.0, 1.0);
  float gamma = acos(cosGamma);

  t2 = degrees(t2rad);
  t3 = degrees(gamma) - 180.0;
  t4 = thetaTotalDeg - t2 - t3;
  return true;
}

bool ikSolve(float x, float y, float z, float thetaTotalDeg, float rollDeg,
             float &t1, float &t2, float &t3, float &t4) {
  float r = sqrt(x * x + z * z);
  float h = y;
  float t1primary = degrees(atan2(z, x));

  if (solveBranch(r, h, thetaTotalDeg, rollDeg, t2, t3, t4)) {
    t1 = t1primary;
    return true;
  }

  float t1flip = (t1primary <= 0) ? t1primary + 180.0 : t1primary - 180.0;
  if (solveBranch(-r, h, thetaTotalDeg, rollDeg, t2, t3, t4)) {
    t1 = t1flip;
    return true;
  }

  return false;
}

void gotoXYZ(float x, float y, float z, float thetaTotalDeg, float rollDeg,
             int steps, int stepDelay) {
  float t1, t2, t3, t4;
  if (!ikSolve(x, y, z, thetaTotalDeg, rollDeg, t1, t2, t3, t4)) {
    Serial.println("goto: target unreachable");
    return;
  }

  int target[6];
  target[0] = angleToUs(t1, WAIST_ANCHOR_DEG, WAIST_ANCHOR_US, INVERT_WAIST, 0);
  target[1] = angleToUs(t2, SHOULDER_ANCHOR_DEG, SHOULDER_ANCHOR_US, INVERT_SHOULDER, 1);
  target[2] = angleToUs(t3, ELBOW_ANCHOR_DEG, ELBOW_ANCHOR_US, INVERT_ELBOW, 2);
  target[3] = angleToUs(t4, WRISTPITCH_ANCHOR_DEG, WRISTPITCH_ANCHOR_US, INVERT_WRISTPITCH, 3);
  target[4] = angleToUs(rollDeg, WRISTROLL_ANCHOR_DEG, WRISTROLL_ANCHOR_US, INVERT_WRISTROLL, 4);
  target[5] = positions[5];

  Serial.print("goto solved: t1=");
  Serial.print(t1); Serial.print(" t2="); Serial.print(t2);
  Serial.print(" t3="); Serial.print(t3); Serial.print(" t4="); Serial.print(t4);
  Serial.print(" roll="); Serial.println(rollDeg);

  moveTo(target, steps, stepDelay);
}

void setup() {
  Serial.begin(115200);
  base.setPeriodHertz(50);       base.attach(9, 500, 2500);
  firstLeg.setPeriodHertz(50);   firstLeg.attach(8, 500, 2500);
  secondLeg.setPeriodHertz(50);  secondLeg.attach(7, 500, 2500);
  thirdLeg.setPeriodHertz(50);   thirdLeg.attach(5, 500, 2500);
  clawAngle.setPeriodHertz(50);  clawAngle.attach(10, 500, 2500);
  claw.setPeriodHertz(50);       claw.attach(2, 500, 2500);
  base.writeMicroseconds(positions[0]);
  firstLeg.writeMicroseconds(positions[1]);
  secondLeg.writeMicroseconds(positions[2]);
  thirdLeg.writeMicroseconds(positions[3]);
  clawAngle.writeMicroseconds(positions[4]);
  claw.writeMicroseconds(positions[5]);
}

Servo* getServo(int n) {
  switch(n) {
    case 0: return &base;
    case 1: return &firstLeg;
    case 2: return &secondLeg;
    case 3: return &thirdLeg;
    case 4: return &clawAngle;
    case 5: return &claw;
    default: return nullptr;
  }
}

void printCoords() {
  String names[] = {"base", "firstLeg", "secondLeg", "thirdLeg", "clawAngle", "claw"};
  for (int i = 0; i < 6; i++) {
    int angle = map(positions[i], 500, 2500, 0, 180);
    Serial.print("Mech. Arm: ");
    Serial.print(names[i]);
    Serial.print(" -> ");
    Serial.print(angle);
    Serial.println(" deg");
  }
}

void moveTo(int target[6], int steps, int stepDelay) {
  int start[6];
  for (int i = 0; i < 6; i++) start[i] = positions[i];
  for (int s = 0; s <= steps; s++) {
    for (int i = 0; i < 6; i++) {
      int cur = start[i] + (target[i] - start[i]) * s / steps;
      getServo(i)->writeMicroseconds(cur);
    }
    delay(stepDelay);
  }
  for (int i = 0; i < 6; i++) {
    positions[i] = target[i];
    getServo(i)->writeMicroseconds(target[i]);
  }
}

void goStraight() {
  moveTo(straightPos, 100, 0);
  printCoords();
}

void goZero() {
  moveTo(zeroPos, 100, 0);
  printCoords();
}

void sayHi() {
  moveTo(straightPos, 100, 0);
  delay(200);
  for (int i = 0; i < 4; i++) {
    clawAngle.writeMicroseconds(1300);
    delay(400);
    clawAngle.writeMicroseconds(1700);
    delay(400);
  }
  clawAngle.writeMicroseconds(1300);
  delay(400);
  clawAngle.writeMicroseconds(1530);
  positions[4] = 1530;
  printCoords();
}

void sayYes() {
  moveTo(straightPos, 100, 10);
  delay(200);
  for (int i = 0; i < 2; i++) {
    moveTo(yesPos, 100, 8);
    delay(200);
    moveTo(straightPos, 100, 8);
    delay(200);
  }
  printCoords();
}

void sayNo() {
  moveTo(straightPos, 100, 10);
  delay(200);
  thirdLeg.writeMicroseconds(1040);
  positions[3] = 1040;
  delay(300);
  for (int i = 0; i < 2; i++) {
    clawAngle.writeMicroseconds(1300);
    delay(400);
    clawAngle.writeMicroseconds(1700);
    delay(400);
  }
  clawAngle.writeMicroseconds(1300);
  delay(400);
  clawAngle.writeMicroseconds(1530);
  positions[4] = 1530;
  printCoords();
}

int calcThirdLeg(int firstUs, int secondUs) {
  float firstContrib  = (firstUs  - 1450) * 1.128;
  float secondContrib = (secondUs - 1500) * 0.825;
  int result = 1080 + (int)(firstContrib + secondContrib);
  result = constrain(result, 500, 2500);
  return result;
}

void goParallelTo(int targetFirst, int targetSecond) {
  if (targetFirst  < 500 || targetFirst  > 2500 ||
      targetSecond < 500 || targetSecond > 2500) {
    return;
  }
  int startFirst  = positions[1];
  int startSecond = positions[2];
  int steps       = 100;
  for (double s = 0; s <= steps; s += 0.25) {
    int curFirst  = startFirst  + (targetFirst  - startFirst)  * s / steps;
    int curSecond = startSecond + (targetSecond - startSecond) * s / steps;
    int curThird  = calcThirdLeg(curFirst, curSecond);
    firstLeg.writeMicroseconds(curFirst);
    secondLeg.writeMicroseconds(curSecond);
    thirdLeg.writeMicroseconds(curThird);
    delay(5);
  }
  positions[1] = targetFirst;
  positions[2] = targetSecond;
  positions[3] = calcThirdLeg(targetFirst, targetSecond);
  printCoords();
}

void rise() {
  int targetFirst  = straightPos[1];
  int targetSecond = straightPos[2];
  int startFirst   = positions[1];
  int startSecond  = positions[2];
  int steps = 100;
  for (int s = 0; s <= steps; s++) {
    int curFirst  = startFirst  + (targetFirst  - startFirst)  * s / steps;
    int curSecond = startSecond + (targetSecond - startSecond) * s / steps;
    int curThird  = calcThirdLeg(curFirst, curSecond);
    firstLeg.writeMicroseconds(curFirst);
    secondLeg.writeMicroseconds(curSecond);
    thirdLeg.writeMicroseconds(curThird);
    delay(10);
  }
  positions[1] = targetFirst;
  positions[2] = targetSecond;
  positions[3] = calcThirdLeg(targetFirst, targetSecond);
  printCoords();
}

void lower() {
  int targetFirst  = zeroPos[1];
  int targetSecond = zeroPos[2];
  int startFirst   = positions[1];
  int startSecond  = positions[2];
  int steps = 100;
  for (int s = 0; s <= steps; s++) {
    int curFirst  = startFirst  + (targetFirst  - startFirst)  * s / steps;
    int curSecond = startSecond + (targetSecond - startSecond) * s / steps;
    int curThird  = calcThirdLeg(curFirst, curSecond);
    firstLeg.writeMicroseconds(curFirst);
    secondLeg.writeMicroseconds(curSecond);
    thirdLeg.writeMicroseconds(curThird);
    delay(10);
  }
  positions[1] = targetFirst;
  positions[2] = targetSecond;
  positions[3] = calcThirdLeg(targetFirst, targetSecond);
  printCoords();
}

void dance() {
  moveTo(straightPos, 100, 10);
  delay(200);
  moveTo(dancePosA, 100, 8);
  delay(200);
  moveTo(straightPos, 100, 8);
  delay(200);
  moveTo(dancePosB, 100, 8);
  delay(200);
  moveTo(straightPos, 100, 8);
  delay(200);
  printCoords();
}

void grab() {
  moveTo(grabPos, 100, 0);
  printCoords();
}

void throwIt() {
  positions[5] = 2050;
  claw.writeMicroseconds(2050);
  delay(1000);
  moveTo(throwPos, 100, 0);
  delay(100);
  positions[5] = 1450;
  claw.writeMicroseconds(1450);
  printCoords();
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input == "coords")   { printCoords();  return; }
    if (input == "straight") { goStraight();   return; }
    if (input == "zero")     { goZero();       return; }
    if (input == "hi")       { sayHi();        return; }
    if (input == "yes")      { sayYes();       return; }
    if (input == "no")       { sayNo();        return; }
    if (input == "rise")     { rise();         return; }
    if (input == "lower")    { lower();        return; }
    if (input == "dance")    { dance();        return; }
    if (input == "grab")     { grab();         return; }
    if (input == "throw")    { throwIt();      return; }
    if (input == "open") {
      positions[5] = 1450;
      claw.writeMicroseconds(1450);
      return;
    }
    if (input == "close") {
      positions[5] = 2050;
      claw.writeMicroseconds(2050);
      return;
    }
    if (input.startsWith("parallel")) {
      int firstSpace  = input.indexOf(' ');
      int secondSpace = input.indexOf(' ', firstSpace + 1);
      if (firstSpace == -1 || secondSpace == -1) return;
      int targetFirst  = input.substring(firstSpace + 1, secondSpace).toInt();
      int targetSecond = input.substring(secondSpace + 1).toInt();
      goParallelTo(targetFirst, targetSecond);
      return;
    }
    if (input.startsWith("goto")) {
      float vals[5];
      int idx = 0;
      int searchStart = 5;
      while (idx < 5) {
        int sp = input.indexOf(' ', searchStart);
        String token = (sp == -1) ? input.substring(searchStart) : input.substring(searchStart, sp);
        token.trim();
        if (token.length() == 0) break;
        vals[idx] = token.toFloat();
        idx++;
        if (sp == -1) break;
        searchStart = sp + 1;
      }
      if (idx < 5) {
        Serial.println("goto: need 5 values -> goto x y z thetaTotal roll");
        return;
      }
      gotoXYZ(vals[0], vals[1], vals[2], vals[3], vals[4], 100, 10);
      return;
    }
    int spaceIndex = input.indexOf(' ');
    if (spaceIndex == -1) return;
    int servoNum = input.substring(0, spaceIndex).toInt();
    int us = input.substring(spaceIndex + 1).toInt();
    if (servoNum < 0 || servoNum > 5) return;
    if (us < 500 || us > 2500) return;
    positions[servoNum] = us;
    getServo(servoNum)->writeMicroseconds(us);
  }
  printCoords();
  delay(100);
}


