#include <ESP32Servo.h>

Servo base, firstLeg, secondLeg, thirdLeg, clawAngle, claw;

int positions[6]   = {1500, 1100, 2500, 1470, 1530, 1450};
int straightPos[6] = {1500, 1450, 1500, 1550, 1530, 1450};
int zeroPos[6]     = {1500, 1100, 2500, 1470, 1530, 1450};
int dancePosA[6]   = {1300, 1300, 1900, 1300, 1530, 1450};
int dancePosB[6]   = {1700, 1300, 1900, 1300, 1530, 1450};
int yesPos[6]      = {1500, 1450, 1500, 1300, 1530, 1450};
int grabPos[6]     = {1500, 1450, 1500, 1100, 1530, 1450};
int throwPos[6]    = {1300, 1450, 1500, 1600, 1530, 2050};

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
