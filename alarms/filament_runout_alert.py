#!/usr/init/env python3
import time
import requests
import os
import sys
from sense_hat import SenseHat

sys.path.append("/usr/lib/python3/dist-packages")

from dotenv import load_dotenv

env_path = "/home/pi/.env"

if not load_dotenv(dotenv_path=env_path):
    print(f"Error: Could not load environment file at {env_path}", file=sys.stderr)
    sys.exit(1)

NTFY_URL = os.getenv("NTFY_URL")  # Update with your ntfy topic
ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'
ALERT_LOCK_FILE = '/tmp/alert_alarm.lock'
PAUSE_LOCK_FILE = '/tmp/pause_alarm.lock'

sense = SenseHat()

def trigger_tier3_filament_alert():
    # SAFETY GUARD: If Tier 1 Fire Alarm is active, abort immediately
    if os.path.exists(ALARM_LOCK_FILE) or os.path.exists(ALERT_LOCK_FILE):
        sys.exit(0)
        
    print("ℹ️ TIER 3 NOTICE: Filament Runout / Non-Urgent Attention Required.")

    with open(PAUSE_LOCK_FILE, 'w') as f:
        f.write('ACTIVE')

    # Send ntfy Priority 2/3 non-urgent alert
    try:
        requests.post(
            NTFY_URL,
            data="ℹ️ PRINTER NOTICE: Filament runout detected. Action required.",
            headers={"Priority": "3", "Title": "FILAMENT RUNOUT"}
        )
    except Exception as e:
        print(f"Failed to send ntfy alert: {e}")
        
    blue = (0, 0, 255)
    black = (0, 0, 0)
    
    try:
        while True:
            # Re-check Tier 1 interlock in loop
            if os.path.exists(ALARM_LOCK_FILE):
                sense.clear()
                sys.exit(0)
                
            # Flashing blue matrix (no horn, completely silent)
            sense.clear(blue)
            time.sleep(0.5)
            sense.clear(black)
            time.sleep(0.5)
            
            # Check for physical Sense HAT joystick press to clear/silence
            for event in sense.stick.get_events():
                if event.action == "pressed":
                    print("Joystick pressed: Clearing Tier 3 filament notice.")
                    sense.clear()
                    if os.path.exists(PAUSE_LOCK_FILE):
                        os.remove(PAUSE_LOCK_FILE)
                    return
                    
    except KeyboardInterrupt:
        if os.path.exists(PAUSE_LOCK_FILE):
            os.remove(PAUSE_LOCK_FILE)
        sense.clear()

if __name__ == "__main__":
    trigger_tier3_filament_alert()
