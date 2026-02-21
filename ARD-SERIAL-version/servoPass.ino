// RC COCKPIT v0.1
// Read rc commands from USB serial and pass to four servos


#include <Servo.h>

// Pins for AETR on Analog pins A0-A3
const int rollPin     = A0; 
const int pitchPin    = A1;
const int throttlePin = A2;
const int yawPin      = A3;

Servo rollServo, pitchServo, throttleServo, yawServo;

void setup() {
  Serial.begin(115200);
  
  rollServo.attach(rollPin);
  pitchServo.attach(pitchPin);
  throttleServo.attach(throttlePin);
  yawServo.attach(yawPin);
  
  // Optional: Set servos to neutral/idle on startup
  rollServo.writeMicroseconds(1500);
  pitchServo.writeMicroseconds(1500);
  throttleServo.writeMicroseconds(1000); // Throttle low
  yawServo.writeMicroseconds(1500);
}

void loop() {
  if (Serial.available() > 0) {
    // Expecting: <roll,pitch,yaw,throttle>
    if (Serial.read() == '<') {
      int r = Serial.parseInt(); // rcCommand[0]
      int p = Serial.parseInt(); // rcCommand[1]
      int y = Serial.parseInt(); // rcCommand[2]
      int t = Serial.parseInt(); // rcCommand[3]
      
      // AETR Output Logic
      rollServo.writeMicroseconds(constrain(r, 1000, 2000));
      pitchServo.writeMicroseconds(constrain(p, 1000, 2000));
      throttleServo.writeMicroseconds(constrain(t, 1000, 2000));
      yawServo.writeMicroseconds(constrain(y, 1000, 2000));
    }
  }
}
