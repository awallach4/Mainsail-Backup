#!/usr/bin/env python3
import time
import requests
import lgpio
from sense_hat import SenseHat
import os
import sys
import threading

sys.path.append("/usr/lib/python3/dist-packages")

from dotenv import load_dotenv

env_path = '/home/pi/.env'

if not load_dotenv(dotenv_path=env_path):
    print(f"Error: Could not load environment file at {env_path}", file=sys.stderr)
    sys.exit(1)

load_dotenv("/home/pi/.env")

PIN_HORN = 17  # BCM pin for transistor-driven active horn (NPN low-side switching)
NTFY_URL = os.getenv("NTFY_URL")  # Update with your ntfy topic
ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'
ALERT_LOCK_FILE = '/tmp/alert_alarm.lock'

sense = SenseHat()
alarm_active = False
reset_event = threading.Event()
state_lock = threading.Lock()
strobe_active = threading.Event()

def joystick_listener_thread():
    global alarm_active
    while True:
        try:
            event = sense.stick.wait_for_event()
            if event and event.action == "pressed":
                with state_lock:
                    if alarm_active:
                        print("Physical joystick pressed: Immediate reset triggered.")
                        alarm_active = False
                        reset_event.set()
        except Exception:
            time.sleep(0.1)

def strobe_worker():
    """Background thread that flashes the Sense HAT matrix like a building strobe (1 Hz cycle)."""
    while True:
        if strobe_active.is_set():
            # Flash ON (Bright White or Red)
            try:
                sense.clear(255, 255, 255)
            except Exception:
                pass
            time.sleep(0.05)  # Flash duration

            # Flash OFF
            try:
                sense.clear(255, 255, 0)
            except Exception:
                pass
            time.sleep(0.95)  # Interval to complete the 1-second cadence
        else:
            time.sleep(0.2)

def trigger_tier2_continuous_alarm(reason):
    print("⚠️ URGENT ALERT: Spaghetti / Failure Detected. Initiating Continuous Short Bursts...")

    if os.path.exists(ALARM_LOCK_FILE):
        print("🚨 Tier 1 Fire Alarm is active! Bypassing auxiliary GPIO operation.")
        sys.exit(0)

    global alarm_active

    with state_lock:
        if alarm_active:
            return
        alarm_active = True
    reset_event.clear()

    with open(ALERT_LOCK_FILE, 'w') as f:
        f.write('ACTIVE')

    # Send ntfy Priority 3 alert for urgent attention
    try:
        requests.post(
            NTFY_URL,
            data=f"⚠️ {reason}",
            headers={"Priority": "4", "Title": "ENDER 3 ALERT"}
        )
    except Exception as e:
        print(f"Failed to send ntfy alert: {e}")

    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_HORN, 0)

    try:
        strobe_active.set()
        while not reset_event.is_set():
            # Short burst ON + Flash Yellow
            lgpio.gpio_write(h, PIN_HORN, 1)  # ON
            time.sleep(0.25)

            # Short burst OFF + Clear Matrix
            lgpio.gpio_write(h, PIN_HORN, 0)  # OFF

            # Check for physical Sense HAT joystick press to silence/reset
            time.sleep(0.25)

            if reset_event.is_set():
                break

    finally:
        lgpio.gpio_write(h, PIN_HORN, 0)
        lgpio.gpiochip_close(h)
        strobe_active.clear()
        sense.clear()
        if os.path.exists(ALERT_LOCK_FILE):
            os.remove(ALERT_LOCK_FILE)
        with state_lock:
            alarm_active = False
            is_manual_drill = False

if __name__ == "__main__":
    threading.Thread(target=strobe_worker, daemon=True).start()
    threading.Thread(target=joystick_listener_thread, daemon=True).start()
    reason = sys.argv[1] if len(sys.argv) > 1 else "Unknown Printer Fault"
    trigger_tier2_continuous_alarm(reason)
