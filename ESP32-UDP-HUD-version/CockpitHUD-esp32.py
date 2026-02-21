# RC Cockpit Simulator v0.3
# a) Parse blackbox log (.CSV) and resample to 50hz
# b) Launch flight video in VLC player
# c) Stream RCcommands, gyro, motor data via UDP
# d) Display realtime HUD in pygame window


import socket
import struct
import pandas as pd
import time
import sys
import pygame
import math
import subprocess
import os

# --- NETWORK & FILE CONFIG ---

# Update with the IP address of your ESP32
UDP_IP = "192.168.0.164"
UDP_PORT = 8888
FILE_PATH = r"C:\path for yur blackbox log.bbl.csv"

# --- VLC CONFIG ---
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
VIDEO_FILE = r"C:\path for your flight video.MP4"

# --- SYNC PARAMETERS ---
# 1. PHYSICAL DELAY: Time (ms) to wait for VLC to open before data starts.
#    increase this if your video is running behind the servos
VLC_STARTUP_DELAY_MS = 0  

# 2. DATA OFFSET: Time (ms) to skip at the beginning of the log file.
#    increase this if your video is running ahead of the servos
DATA_OFFSET_MS = 80  

# 3. TIME SCALING (RESTORED):
# use this if the timer on your blackbox log is slower/faster than the flight video
# (it starts in sync, but by the end of the flight they are out of sync)
# for example if your video is 500 seconds, but the log is only 498.2 seconds 
# using 1.0035 stretches the log to match the slightly longer video.
TIME_SCALE = 1.00

# --- TIMING ---
STREAM_HZ = 50            
# The interval is calculated using your specific scaling factor
INTERVAL = (1.0 / STREAM_HZ) * TIME_SCALE

# Display Settings
WIN_W, WIN_H = 800, 600
HUD_CY, STICK_CY = 220, 500
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- PYGAME SETUP ---
pygame.init()
screen = pygame.display.set_mode((WIN_W, WIN_H))
pygame.display.set_caption(f"Drone Ground Station | Scale: {TIME_SCALE}")
font = pygame.font.SysFont("Consolas", 16)

def find_header_row(path):
    """Scans the CSV to find the Betaflight header row."""
    keywords = ['loopIteration', 'time', 'rcCommand', 'gyroADC', 'motor']
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if sum(1 for word in keywords if word in line) >= 4:
                return i
    return None

def draw_arrow(surf, center, size, dir_type, color):
    """Draws HUD arrows for Pitch and Yaw."""
    x, y = center
    if dir_type == 0: pts = [(x, y-size), (x-size, y), (x+size, y)]
    elif dir_type == 1: pts = [(x, y+size), (x-size, y), (x+size, y)]
    elif dir_type == 2: pts = [(x-size, y), (x, y-size), (x, y+size)]
    else: pts = [(x+size, y), (x, y-size), (x, y+size)]
    pygame.draw.polygon(surf, color, pts)

def apply_curve(value, midpoint, factor, input_range):
    """Applies the reverse expo throttle curve logic."""
    normalized = (value - midpoint) / (input_range / 2)
    if normalized >= 0:
        shaped = normalized * (1 - factor) + factor * (normalized ** 2)
    else:
        shaped = normalized * (1 - factor) - factor * (normalized ** 2)
    return midpoint + shaped * (input_range / 2)

def run_replayer():
    header_idx = find_header_row(FILE_PATH)
    if header_idx is None: 
        print("Header not found!"); return

    vlc_process = None

    try:
        # --- 1. DATA PRE-PROCESSING ---
        print(f"Loading data with Scale: {TIME_SCALE}...")
        df = pd.read_csv(FILE_PATH, skiprows=header_idx)
        df.columns = [c.replace('H,', '').replace('H ', '').strip() for c in df.columns]

        time_col = next((c for c in df.columns if 'time' in c.lower()), None)
        rc_cols = [next(c for c in df.columns if f'rcCommand[{i}]' in c) for i in range(4)]
        gyro_cols = [next(c for c in df.columns if f'gyroADC[{i}]' in c) for i in range(3)]
        motor_cols = [next(c for c in df.columns if f'motor[{i}]' in c) for i in range(4)]
        
        # Resampling logic to keep data at 50Hz
        raw_times = pd.to_numeric(df[time_col], errors='coerce')
        df['timestamp'] = pd.to_timedelta(raw_times - raw_times.dropna().iloc[0], unit='us')
        df = df.set_index('timestamp').dropna(subset=[time_col])
        df_resampled = df[rc_cols + gyro_cols + motor_cols].resample('20ms').mean().ffill().dropna()

        # Prepare packed binary rows
        data_rows = []
        for row in df_resampled.values:
            r = list(map(int, row))
            for i in range(3): r[i] += 1500 
            r[3] = int(apply_curve(r[3], 1450, -0.8, 800)) 
            data_rows.append(tuple(r))

        packed_blobs = [struct.pack('11i', *r) for r in data_rows]
        time_labels = [str(t).split('0 days ')[-1][:11].lstrip('0:') for t in df_resampled.index]
        total = len(data_rows)

        # Calculate skip frames based on 20ms resample rate
        skip_frames = int(DATA_OFFSET_MS / 20)
        
        # --- 2. STARTUP SEQUENCE ---
        print(f"Ready: {total} frames. Offset: {skip_frames} frames.")
        print("\n" + "="*40)
        input("Press ENTER to start VLC and Stream...")

        # Launch VLC
        #        vlc_process = subprocess.Popen([VLC_PATH, VIDEO_FILE, "--fullscreen", "--no-video-title-show"])
        # --- VLC WINDOW CONFIG ---
        # --- VLC CONFIG ---
        # This will open VLC on the entire screen, but shrink the video itself.
        # Adjust ZOOM_LEVEL: 0.5 is half size, 0.75 is 3/4 size.
        ZOOM_LEVEL = "0.5" 

        # ... inside run_replayer() ...

        vlc_args = [
            VLC_PATH, 
            VIDEO_FILE,
            "--fullscreen",
            "--no-video-title-show",
#            "--no-embedded-video",     # Often required for zoom to work in fullscreen
            "--zoom", ZOOM_LEVEL,
#            "--video-align=0",          # 0=Center, 1=Left, 2=Right, 4=Top, 8=Bottom
            "--no-qt-fs-controller"    # Hides the "pop up" controller in fullscreen
        ]

        vlc_process = subprocess.Popen(vlc_args)

        # Physical delay before stream begins
        time.sleep(VLC_STARTUP_DELAY_MS / 1000.0)

        # --- 3. REPLAY LOOP (Single Pass) ---
        print("Streaming...")
        start_perf = time.perf_counter()
        
        for i in range(skip_frames, total):
            # Precision timing anchored to system clock
            # (i - skip_frames) ensures the timer starts at 0 for the first frame sent
            target_time = start_perf + ((i - skip_frames) * INTERVAL)
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT: return

            # Send UDP packet to ESP32
            sock.sendto(packed_blobs[i], (UDP_IP, UDP_PORT))
            row = data_rows[i]
            
            # --- HUD RENDERING ---
            screen.fill((15, 15, 20)) 
            CX = WIN_W // 2

            # Background HUD Elements
            pygame.draw.circle(screen, (40, 60, 80), (CX, HUD_CY), 150, 1) 
            pygame.draw.circle(screen, (70, 90, 120), (CX, HUD_CY), 100, 2)
            pygame.draw.line(screen, (50, 50, 70), (CX, HUD_CY-150), (CX, HUD_CY+150), 1)
            pygame.draw.line(screen, (50, 50, 70), (CX-150, HUD_CY), (CX+150, HUD_CY), 1)

            # Roll/Pitch/Yaw HUD
            angle = math.radians(row[4])
            rx, ry = CX + 100*math.sin(angle), HUD_CY - 100*math.cos(angle)
            pygame.draw.rect(screen, (0, 255, 255), (rx-6, ry-6, 12, 12)) 
            p_y = int(max(min(HUD_CY + (row[5] * 0.3), HUD_CY+145), HUD_CY-145))
            draw_arrow(screen, (CX, p_y), 10, (1 if row[5] >= 0 else 0), (255, 255, 0))
            y_x = int(max(min(CX + (row[6] * -0.3), CX+145), CX-145))
            draw_arrow(screen, (y_x, HUD_CY), 10, (2 if row[6] >= 0 else 3), (255, 0, 255))

            # Motor Power Columns
            m_x_pos = [CX-240, CX-200, CX+200, CX+240]
            for m_idx in range(4):
                val = row[7 + m_idx]
                h = int((val / 2000) * 200)
                x = m_x_pos[m_idx]
                base = HUD_CY + 100
                pygame.draw.rect(screen, (40, 40, 40), (x, HUD_CY-100, 25, 200), 1)
                h_g = min(h, 120); h_o = min(max(h-120, 0), 40); h_r = max(h-160, 0)
                if h_g: pygame.draw.rect(screen, (0, 180, 0), (x, base-h_g, 25, h_g))
                if h_o: pygame.draw.rect(screen, (200, 140, 0), (x, base-120-h_o, 25, h_o))
                if h_r: pygame.draw.rect(screen, (220, 0, 0), (x, base-160-h_r, 25, h_r))

            # RC Stick Indicators
            box_sz = 140; box_h = box_sz // 2
            lx_c, rx_c = CX - 90, CX + 90; sf = box_h / 500.0 
            l_x, l_y = lx_c + (row[2]-1500)*sf, STICK_CY - (row[3]-1500)*sf
            r_x, r_y = rx_c + (row[0]-1500)*sf, STICK_CY - (row[1]-1500)*sf
            pygame.draw.rect(screen, (100, 100, 100), (lx_c-box_h, STICK_CY-box_h, box_sz, box_sz), 2)
            pygame.draw.rect(screen, (100, 100, 100), (rx_c-box_h, STICK_CY-box_h, box_sz, box_sz), 2)
            pygame.draw.circle(screen, (255, 50, 50), (int(l_x), int(l_y)), 7)
            pygame.draw.circle(screen, (255, 50, 50), (int(r_x), int(r_y)), 7)

            # Frame Counter & Log Time
            row_txt = font.render(f"FRAME: {i+1} / {total}", True, (200, 200, 200))
            time_txt = font.render(f"LOG TIME: {time_labels[i]}", True, (0, 255, 100))
            screen.blit(row_txt, (20, WIN_H - 55))
            screen.blit(time_txt, (20, WIN_H - 30))

            pygame.display.flip()

            # High-precision wait
            while time.perf_counter() < target_time: 
                pass
            
        print("Playback finished.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("\n[FINISHING] Closing all resources...")
        
        # 1. Kill VLC immediately and forcefully
        if vlc_process:
            try:
                # Taskkill /T kills the entire 'tree' of windows (including Direct3D)
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(vlc_process.pid)], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass 

        # 2. Release the UDP Socket
        try:
            sock.close()
            print("Socket closed.")
        except:
            pass

        # 3. Shutdown Pygame
        pygame.quit()

        # 4. Final Handshake with IDE
        print("Exit sequence complete. Releasing IDE...")
        time.sleep(0.5) # Give the OS half a second to clean up the taskkill
        
        # We use both to ensure the IDE sees the termination
        sys.stdout.flush() 
        os._exit(0)

if __name__ == "__main__":
    run_replayer()