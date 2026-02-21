\# RC Cockpit Simulator ✈️

This project simulates a cockpit view with moving pilot arms and a cockpit dashboard by streaming flight telemetry data from a PC (via a Python script) to a microcontroller. It controls physical servos for arm motion and features a real-time Heads-Up Display (HUD) displaying motors and gyro data. When synced with the flight video, it provides a virtual cockpit view in flight. Flight telemetry is taken from a Betaflight blackbox log.

![IMG20260213182014](https://github.com/user-attachments/assets/d1ccf526-c34a-40e3-9b84-aaa3c4a6a8fd)

Here is a run of the ESP32 version. The cockpit was overlaid onto the flight video using green screen as that allowed the flight video quality to be maintained (filming the model in front of a screen was a little fuzzy) and only roll, pitch, and throttle are used.

https://youtu.be/WE5VddACYq4


This repository includes two versions of the project:  
1\. \*\*Version 1 (Current):\*\* ESP32 over WiFi (UDP) with a real-time HUD and VLC video synchronization.  
2\. \*\*Version 2 (Legacy):\*\* Arduino over USB (Serial) for basic servo control.

(ArduinoMega with servo shield… humongous   vs   TTGO T-Display ESP32… compact)![][image2]
![IMG20260214195821](https://github.com/user-attachments/assets/f8f69b99-612c-4dc2-909e-00714e1f78c0)


\#\# 🚀 Version 1: ESP32 \+ UDP \+ HUD \+ Video Sync (Current)

This version streams a packed binary structure from Python to an ESP32 over a local WiFi network using UDP. The ESP32 drives 4 servos and renders a real-time HUD on its onboard display. The Python script automatically launches VLC media player to play your flight video, and with some timing parameters it can be set to perfectly synchronize with the telemetry data stream.

\#\#\# Hardware Required  
\* \*\*ESP32 TTGO T-Display\*\* (1.14" 240x135 TFT) \-   
   (most ESP32 boards should work for the servos, different displays may need some tailoring)  
\* 1-4x Servos  
\* 5V Power Supply for the Servos  
\* Model of the cockpit/pilot that moves with the servos  
For the cockpit panel, I used this 3D print which comes with images for the dials  
[https://www.thingiverse.com/thing:2204755](https://www.thingiverse.com/thing:2204755)

\#\#\# Software & Libraries  
\* \*\*Arduino IDE\*\* (with ESP32 board manager installed)  
\* \[TFT\_eSPI\](https://github.com/Bodmer/TFT\_eSPI) (For the display. \*Note: You must configure \`User\_Setup.h\` for the ST7789 135x240 display\*)  
\* \[ESP32Servo\](https://github.com/madhephaestus/ESP32Servo)  
\* \*\*Python 3.x\*\* with \`pygame\` and \`pandas\` (\`pip install pygame pandas\`)  
\* \*\*VLC Media Player\*\* installed on your PC.

\#\#\# Step 1: ESP32 Setup  
1\. Open the \`CockpitHUDesp32.ino\` sketch in the Arduino IDE.  
2\. \*\*CRITICAL:\*\* Update the WiFi credentials at the top of the sketch to match your local network:  
   const char\* ssid     \= "YOUR\_WIFI\_NAME";  
   const char\* password \= "YOUR\_WIFI\_PASSWORD";

3. Flash the code to your ESP32.  
4. Once booted, the ESP32 will display a radar sweep animation and its **Local IP Address**. Note this IP address down.  
5. Note that the servos are setup on the following pins. Update this line if you want to have them on different pins. Only connect servos you want to use.  
   const int servoPins\[4\] \= {13, 12, 17, 15};   // roll, pitch, yaw, throttle

### **Step 2: Python Script Configuration**

Open `CockpitHUD-esp32.py` and update the configuration block at the very top before running:

1. **Network Sync:** \* Set `UDP_IP` to the exact IP address shown on your ESP32's screen.  
2. **File Paths:**  
   * `FILE_PATH`: Set this to the location of your flight log CSV file.  
   * `VIDEO_FILE`: Set this to the location of your MP4 flight video.  
   * `VLC_PATH`: Verify the path to your `vlc.exe` (usually `C:\Program Files\VideoLAN\VLC\vlc.exe`).  
3. **Video Synchronization Tuning:**  
   * `VLC_STARTUP_DELAY_MS`: VLC takes a moment to open and enter fullscreen. Adjust this delay (e.g., `2500` for 2.5 seconds) so the data stream waits for the video to actually appear before sending the first packet. If VLC opens faster than the streaming, instead increase DATA\_OFFSET\_MS.  
   * `TIME_SCALE`: Flight logs and video framerates often drift over long flights. Use this multiplier to perfectly align them. (e.g., `1.0035` slightly stretches the data duration to match a longer video).

### **Step 3: Launch**

Run the Python script. It will parse the CSV, open a pygame window for the simulated HUD on the PC, and then wait for you to press enter. It will then automatically launch VLC in a zoomed-out fullscreen window, and trigger the ESP32 to the live "Flight HUD" mode and start streaming to the servos. When the video ends, VLC will safely close and the ESP32 will display a "Simulation Terminated". If you want to rerun the python script, you may need to press STOP first, before pressing play.

---

## **📦 The Flight Telemetry**

The flight telemetry is taken from a Betaflight Blackbox log. The log file (.bbl) needs to be converted to a (.csv) format which can be done using Blackbox explorer. The python script will then parse and resample the blackbox data down to 50hz for streaming. 50hz was selected as most servos support this refresh rate.  
The data sampled:  
	**RCcommand** : basically the stick controls. Roll, Pitch, Yaw are stored in a range of \-500 to 500, so 1500 is added to convert them to the 1000-2000 microsecond range recognized by servo PWM. The Throttle is already stored in this 1000-2000 range.  
	**Gyro** : this is the gyro data in degrees/second. This is just used to drive the center HUD display.  
	**Motors** : this is the motor output, also stored in the 1000-2000 range. This is just used for driving the HUD display.  
---

## **📦 The Binary Packet Structure**

Presently, stick commands, gyro, and motor data is streamed. If you want to write your own data sender, the ESP32 expects a 44-byte binary payload structured as 11 consecutive 32-bit integers (`int32_t`).

C++  
struct PacketData {  
  int32\_t rc\[4\];      // Bytes 0-15: Roll, Pitch, Yaw, Throttle  
  int32\_t gyro\[3\];    // Bytes 16-27: Gyro Roll, Pitch, Yaw  
  int32\_t motors\[4\];  // Bytes 28-43: Motor 0, 1, 2, 3 RPMs  
} \_\_attribute\_\_((packed));

---

## **🔌 Version 2: Arduino \+ USB Serial (Legacy)**

This older version streams telemetry data (RCcommand) from Python to a standard Arduino over a USB Serial connection and controls four servos. This was just a quick mockup to see how this would look and can be setup relatively quickly if you have an arduino+servo shield laying around.

### **Installation & Usage**

1. Open the Arduino sketch (`servoPass.ino`) and flash it to your board.  
2. Note the COM port your Arduino is connected to (e.g., `COM3`).  
3. Open the legacy Python script (`BBStream.py`) and update the serial port variable to match.  
4. `FILE_PATH`: Set this to the location of your flight log CSV file.

Here is a run using the arduino version. This is the model filmed in front of a PC monitor.

[https://youtu.be/cBl0tHdTQ\_Y](https://youtu.be/cBl0tHdTQ_Y)

All coding and most documentation was done with Gemini. Ideas and debugging was still done by a human ;P  
But it is amazing this project was completed without needing to write a single line of code\!
