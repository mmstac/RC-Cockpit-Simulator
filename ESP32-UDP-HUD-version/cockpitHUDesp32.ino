// RC COCKPIT SIMULATOR ESP32 HUD v0.3
// This will receive a UDP datastream via wifi and
// a) update a realtime HUD (Heads Up Display)
// b) pass rc commands stream to four servos


#include <WiFi.h>
#include <WiFiUdp.h>
#include <ESP32Servo.h>
#include <TFT_eSPI.h>
#include <SPI.h>

// --- CONFIGURATION ---
const char* ssid     = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
const int   udpPort  = 8888;

// Pins for TTGO T-Display & Servos
const int servoPins[4] = {13, 12, 17, 15};   // roll, pitch, yaw, throttle
const int motorX[4]    = {5, 25, 200, 220};

// UI Dimensions
const int SCREEN_W = 240; 
const int HUD_W = 160;
const int HUD_H = 135;
const int HUD_X = 40;
const int CX = HUD_W / 2;
const int CY = HUD_H / 2;

// --- STATE MANAGEMENT ---
enum AppState { STATE_WAITING, STATE_ACTIVE, STATE_TERMINATED };
AppState currentState = STATE_WAITING;
unsigned long lastPacketTime = 0;
const unsigned long TIMEOUT_MS = 2000;

// Radar Animation Settings
int radarCx = SCREEN_W / 2;
int radarCy = 70;
int radarLen = 45;
int radarAngle = 0;

// Binary Packet Structure (11 integers = 44 bytes)
struct PacketData {
  int32_t rc[4];      // 0-3
  int32_t gyro[3];    // 4-6 (Roll, Pitch, Yaw)
  int32_t motors[4];  // 7-10
} __attribute__((packed));

// Global Objects
PacketData data;
WiFiUDP udp;
TFT_eSPI tft = TFT_eSPI(); 
TFT_eSprite hudSprite = TFT_eSprite(&tft);
Servo servos[4];

// State Variables
int prevHeights[4] = {0, 0, 0, 0};
unsigned long frameCount = 0;

// --- STARTUP & TERMINATION SCREENS ---

void drawStartupStatic() {
  tft.fillScreen(TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  tft.setTextSize(2);
  tft.drawString("Cockpit Simulator", SCREEN_W / 2, 15);
  tft.drawString("v0.3", 190, 35);
  
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(1);
  tft.drawString("Waiting...", 60, 125);
  tft.drawString(WiFi.localIP().toString(), 190, 125);
  
  tft.drawCircle(radarCx, radarCy, radarLen, TFT_DARKGREY);
}

void animateRadar() {
  float oldRad = (radarAngle * 0.0174533);
  tft.drawLine(radarCx, radarCy, radarCx + cos(oldRad)*radarLen, radarCy + sin(oldRad)*radarLen, TFT_BLACK);

  radarAngle = (radarAngle + 6) % 360;

  float newRad = (radarAngle * 0.0174533);
  tft.drawLine(radarCx, radarCy, radarCx + cos(newRad)*radarLen, radarCy + sin(newRad)*radarLen, TFT_GREEN);
  delay(15);
}

void drawTerminationScreen() {
  tft.fillScreen(TFT_BLACK);
  tft.drawRect(10, 10, SCREEN_W - 20, 115, TFT_RED);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_RED, TFT_BLACK);
  tft.setTextSize(2);
  tft.drawString("SIMULATION", SCREEN_W / 2, 50);
  tft.drawString("TERMINATED", SCREEN_W / 2, 80);
}

// --- HELPER: DRAW ARROWS ON SPRITE ---
void drawArrow(int x, int y, int size, int dir, uint16_t color) {
  // 0:Up, 1:Down, 2:Left, 3:Right
  int width = 3;
  if (dir == 0)      hudSprite.fillTriangle(x, y - width, x - size, y + width, x + size, y + width, color);
  else if (dir == 1) hudSprite.fillTriangle(x, y + width, x - size, y - width, x + size, y - width, color);
  else if (dir == 2) hudSprite.fillTriangle(x - width, y, x + width, y - size, x + width, y + size, color);
  else if (dir == 3) hudSprite.fillTriangle(x + width, y, x - width, y - size, x - width, y + size, color);
}

// --- HUD UPDATE (SPRITE) ---
void updateHUD(int32_t r, int32_t p, int32_t y) {
  hudSprite.fillSprite(TFT_BLACK);
  // Draw Static Elements
  hudSprite.drawFastVLine(CX, 1, HUD_H - 1, 0x5AAB);
  // Vertical Crosshair
  hudSprite.drawFastHLine(10, CY, HUD_W - 20, 0x5AAB); // Horizontal Crosshair
  hudSprite.drawCircle(CX, CY, 45, 0x39C7);
  // Roll Ring
  hudSprite.drawCircle(CX, CY, 67, 0x39C7);           // Roll Ring

  // 1. Roll (Diamond) - r is degrees
  float angle = (constrain(r,-180,180) * PI) / 180.0;
  int rx = CX + (int)(45 * sin(angle));
  int ry = CY - (int)(45 * cos(angle));
  hudSprite.fillSmoothRoundRect(rx - 4, ry - 4, 8, 8, 2, TFT_CYAN);
  // 2. Pitch (Vertical Arrow) - p is deg/s
  int py = map(constrain(p, -150, 150), 150, -150, HUD_H - 15, 15);
  drawArrow(CX, py, 8, (p >= 0 ? 1 : 0), TFT_YELLOW);
  // 3. Yaw (Horizontal Arrow) - y is deg/s
  int yx = map(constrain(y, -250, 250), 250, -250, 15, HUD_W - 15);
  drawArrow(yx, CY, 10, (y >= 0 ? 2 : 3), TFT_MAGENTA);

  hudSprite.pushSprite(HUD_X, 0);
}

// --- MOTOR BARS (DIRECT DRAW) ---
void updateMotorBar(int i, int32_t val) {
  int h = map(constrain(val, 0, 2000), 0, 2000, 0, 135);
  int x = motorX[i];
  
  if (h > prevHeights[i]) {
    for (int py = prevHeights[i]; py < h; py++) {
      uint16_t c = TFT_GREEN;
      if (py > 108) c = TFT_RED;        // >80%
      else if (py > 67) c = 0xFD20;     // 50-80% (Orange/Yellow)
      tft.drawFastHLine(x, 134 - py, 15, c);
    }
  } else if (h < prevHeights[i]) {
    tft.fillRect(x, 134 - prevHeights[i], 15, prevHeights[i] - h, TFT_BLACK);
  }
  prevHeights[i] = h;
}

void setup() {
  Serial.begin(115200);

  // 1. Initialize Display & Sprite
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(TFT_BLACK);
  hudSprite.createSprite(HUD_W, HUD_H);

  // 2. Initialize Servos
  for(int i = 0; i < 4; i++) {
    servos[i].attach(servoPins[i]);
  }

  // 3. Connect WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  udp.begin(udpPort);
  Serial.println("\nReady.");

  drawStartupStatic(); 
}

void loop() {
  unsigned long currentMillis = millis();
  int packetSize = udp.parsePacket();

  // --- 1. PROCESS INCOMING DATA ---
  if (packetSize > 0) {
    udp.read((uint8_t*)&data, sizeof(PacketData));
    lastPacketTime = currentMillis;

    // Transition from Waiting/Terminated -> Active
    if (currentState == STATE_WAITING || currentState == STATE_TERMINATED) {
      tft.fillScreen(TFT_BLACK);
      for(int i=0; i<4; i++) prevHeights[i] = 0; // Clear bar memory
      currentState = STATE_ACTIVE;
    }
  }

  // --- 2. EXECUTE STATE BEHAVIOR ---
  switch (currentState) {
    case STATE_WAITING:
      animateRadar();
      break;

    case STATE_ACTIVE:
      // Only redraw HUD/Servos if we actually received fresh data this loop
      if (packetSize > 0) {
        // 1. Move Servos
        for(int i = 0; i < 4; i++) {
          servos[i].writeMicroseconds(data.rc[i]);
        }
        // 2. Update Motor Bars (Left/Right)
        for(int i = 0; i < 4; i++) {
          updateMotorBar(i, data.motors[i]);
        }
        // 3. Update Center HUD (Roll, Pitch, Yaw)
        updateHUD(data.gyro[0], data.gyro[1], data.gyro[2]);
      }

      // 4. Check for Timeout
      if (currentMillis - lastPacketTime > TIMEOUT_MS) {
        drawTerminationScreen();
        currentState = STATE_TERMINATED;
      }
      break;

    case STATE_TERMINATED:
      // Holds the red screen. If a new packet arrives, Step 1 catches it
      // and immediately flips the state back to STATE_ACTIVE.
      break;
  }
}
