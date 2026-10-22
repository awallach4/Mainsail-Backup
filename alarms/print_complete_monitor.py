#!/usr/bin/env python3
import time
import requests
import os
from sense_hat import SenseHat

ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'
ALERT_LOCK_FILE = '/tmp/alert_alarm.lock'
PAUSE_LOCK_FILE = '/tmp/pause_alarm.lock'
MOONRAKER_API = "http://127.0.0.1:7125/printer/objects/query?print_stats"
KASA_STATUS_URL = "http://127.0.0.1:9991/status"
sense = SenseHat()

def monitor_loop():
    solid_green = (0, 255, 0)
    last_state = None
    print("Print complete matrix monitor started.")
    
    while True:
        try:
            # SAFETY: Never override Tier 1 fire alarm
            if os.path.exists(ALARM_LOCK_FILE) or os.path.exists(ALERT_LOCK_FILE) or os.path.exists(PAUSE_LOCK_FILE):
                time.sleep(3)
                continue
                
            # Check Kasa plug status first: if power is OFF, clear the matrix
            try:
                kasa_resp = requests.get(KASA_STATUS_URL, timeout=1.0)
                if kasa_resp.status_code == 200 and kasa_resp.text.strip() == 'off':
                    sense.clear()
                    last_state = 'off'
                    time.sleep(5)
                    continue
            except Exception:
                pass  # Kasa daemon unreachable or unneeded

            # Query Moonraker print stats
            resp = requests.get(MOONRAKER_API, timeout=2.0)
            if resp.status_code == 200:
                data = resp.json().get('result', {}).get('status', {})
                print_state = data.get('print_stats', {}).get('state', '')
                
                if print_state == 'complete' and last_state != 'complete':
                    print("Print complete detected: Setting matrix to solid green.")
                    sense.clear(solid_green)
                elif print_state == 'printing' and last_state == 'complete':
                    print("New print started: Clearing matrix.")
                    sense.clear()
                    
                last_state = print_state
                
        except Exception as e:
            print(f"Matrix monitor error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    monitor_loop()
