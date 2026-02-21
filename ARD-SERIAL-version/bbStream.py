# Stream Blackbox RCcommands to serial

import pandas as pd
import serial
import time
import sys

# --- CONFIGURATION ---
FILE_PATH = r"C:\path for your blackbox log.bbl.csv"
PORT = 'COM3'
BAUD = 115200
UPDATE_RATE_HZ = 50
WINDOW_MS = 20

TIMESCALE = 1.003

def find_header_row(file_path):
    """Finds the line number where the CSV data header starts."""
    with open(file_path, 'r') as f:
        for i, line in enumerate(f):
            if 'time' in line and 'rcCommand[0]' in line:
                return i
    return None

def apply_curve(value, midpoint, factor, input_range):
    # Normalize the value to a range of -1 to 1
    normalized_value = (value - midpoint) / (input_range / 2)
    
    # Apply the reverse expo shaping with factor (0.1 to 1.0)
    # This formula provides amplified center sensitivity without extreme overshoot
    
    if normalized_value >= 0:
        shaped_normalized = normalized_value * (1 - factor) + factor * (normalized_value ** 2)
    else:
        shaped_normalized = normalized_value * (1 - factor) - factor * (normalized_value ** 2)

    # Scale back to the original PWM range
    shaped_value = midpoint + shaped_normalized * (input_range / 2)
    
    # Crucial: Clamp the value to ensure it stays within the valid range
    min_val = midpoint - (input_range / 2)
    max_val = midpoint + (input_range / 2)
    
    return max(min_val, min(max_val, shaped_value))

def stream_to_arduino():
    print(f"Loading and resampling log file...")
    
    # 1. Open Blackbox CSV and locate data
    header_idx = find_header_row(FILE_PATH)
    if header_idx is None:
        print(f"Error: Could not find data header in {FILE_PATH}.")
        return

    try:
        print(f"Header found at line {header_idx}. Loading log file...")
        df_full = pd.read_csv(FILE_PATH, skiprows=header_idx)
        df_full.columns = df_full.columns.str.strip()

        gyro_cols = ['gyroADC[0]', 'gyroADC[1]', 'gyroADC[2]']
        rc_cols = ['rcCommand[0]', 'rcCommand[1]', 'rcCommand[2]', 'rcCommand[3]']
        target_cols = ['time'] + rc_cols + gyro_cols
        df = df_full[target_cols].copy()
        
        #scale time and resample data down to 20hz
        start_time = df['time'].min()
        df['bin'] = (round((df['time'] - start_time) * TIMESCALE)) // (WINDOW_MS * 1000)
        resampled = df.groupby('bin').mean().reset_index()
        
    except Exception as e:
        print(f"File Error: {e}")
        return
    
    # 3. Serial Connection and Streaming
    # Use 'with' to ensure the port is closed NO MATTER WHAT
    try:
        with serial.Serial(PORT, BAUD, timeout=1) as ser:
            print(f"Connected to Arduino on {PORT}. Waiting for reset...")
            time.sleep(2) # Crucial for Mega 2560
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # Wait for user to start streaming
            print("\n" + "="*40)
            user_input = input("Press Enter to start streaming: ").lower()
    
            print("Streaming started!")
            start_wall_time = time.time()

            for i, row in resampled.iterrows():              
                # Force convert to int BEFORE creating the string
#                pwm0 = int(1500-(row['rcCommand[0]'])) # Roll
#                pwm1 = int(1500-(row['rcCommand[1]'])) # Pitch
#                pwm2 = int(1500-(row['rcCommand[2]'])) # Yaw
#                pwm0 = int(1500+(row['rcCommand[0]'])) # Roll
#                pwm1 = int(1500+(row['rcCommand[1]'])) # Pitch
                pwm0 = int(apply_curve((1500+row['rcCommand[0]']), 1500, -1.2, 1000)) # Roll
                pwm1 = int(apply_curve((1500+row['rcCommand[1]']), 1500, -1.2, 1000)) # Roll
                pwm2 = int(1500+(row['rcCommand[2]'])) # Yaw
#                pwm3 = int((row['rcCommand[3]']/1.5))        # Throttle
                pwm3 = int(apply_curve(row['rcCommand[3]'], 1450, -0.8, 800))        # Throttle

                target_time = i * (WINDOW_MS / 1000.0)
                while (time.time() - start_wall_time) < target_time:
                    pass

                packet = f"<{pwm0},{pwm1},{pwm2},{pwm3}>\n"
                ser.write(packet.encode())

                if i % 5 == 0: # Update UI every 5 frames to save CPU
                    sys.stdout.write(f"\rSending: {packet.strip()} | Time: {target_time:.2f}s")
                    sys.stdout.flush()


            # 4. Return to Center Logic
            print("\n\nLog finished. Returning servos to center...")
            # Neutral: R:1500, P:1500, Y:1500, Throttle: 1000
            ser.write(b"<1500,1500,1500,1000,0,0,0>\n")
            time.sleep(1) # Give servos time to move before closing port

    except serial.SerialException as e:
        print(f"\nSerial Error: {e}")
        print("TIP: Press Ctrl+F2 in Thonny and try again.")
    except KeyboardInterrupt:
        print("\nStreaming stopped by user.")
    
    print("\nPort closed safely.")

if __name__ == "__main__":
    stream_to_arduino()