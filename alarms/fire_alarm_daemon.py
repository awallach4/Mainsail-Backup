#!/usr/bin/env python3
import time
import requests
import lgpio
from sense_hat import SenseHat
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import subprocess
import os
import sys

sys.path.append("/usr/lib/python3/dist-packages")

from dotenv import load_dotenv

env_path = '/home/pi/.env'

if not load_dotenv(dotenv_path=env_path):
    print(f"Error: Could not load environment file at {env_path}", file=sys.stderr)
    sys.exit(1)

load_dotenv("/home/pi/.env")

SENSE_TEMP_THRESHOLD = 60.0
KASA_HTTP_URL = "http://127.0.0.1:9991/off"
IR_OFF_URL = "http://127.0.0.1:9992/off"
NTFY_URL = os.getenv("NTFY_URL")
ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'

PIN_HORN = 17
sense = SenseHat()
reset_event = threading.Event()
state_lock = threading.Lock()
strobe_active = threading.Event()

alarm_active = False
is_manual_drill = False

def joystick_listener_thread():
    global alarm_active, is_manual_drill
    while True:
        try:
            event = sense.stick.wait_for_event()
            if event and event.action == "pressed":
                with state_lock:
                    if alarm_active:
                        print("Physical joystick pressed: Immediate reset triggered.")
                        alarm_active = False
                        is_manual_drill = False
                        reset_event.set()
                notify_moonraker_off()
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
                sense.clear(255, 0, 0)
            except Exception:
                pass
            time.sleep(0.95)  # Interval to complete the 1-second cadence
        else:
            time.sleep(0.2)

def trigger_tier1_fire_emergency(source_label="THERMAL RUNAWAY / FIRE DETECTED", manual=False):
    global alarm_active, is_manual_drill
    
    with state_lock:
        if alarm_active:
            return  
        alarm_active = True
        is_manual_drill = manual
        
    reset_event.clear()
    print(f"🔥 EMERGENCY TRIGGERED ({'DRILL' if manual else 'REAL'}): {source_label}! Executing Tier 1...")
    
    try:
        subprocess.run(["pkill", "-f", "urgent_march_alarm.py"], check=False)
    except Exception as e:
        print(f"Error terminating Tier 2 process: {e}")

    with open(ALARM_LOCK_FILE, 'w') as f:
        f.write('ACTIVE')
    
    try:
        requests.get(KASA_HTTP_URL, timeout=2.0)
    except Exception as e:
        print(f"Failed to cut Kasa plug: {e}")
        
    try:
        requests.get(IR_OFF_URL, timeout=2.0)
    except Exception as e:
        print(f"Failed to turn off IR lights: {e}")
        
    try:
        requests.post(
            NTFY_URL,
            data=f"🚨 CRITICAL FIRE EMERGENCY: {source_label}",
            headers={"Priority": "5", "Title": "ENDER 3 FIRE ALARM"}
        )
    except Exception as e:
        print(f"Failed to send ntfy alert: {e}")
        
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_HORN, 0)

    try:
        strobe_active.set()
        while not reset_event.is_set():
            for _ in range(3):
                if reset_event.is_set():
                    break
                lgpio.gpio_write(h, PIN_HORN, 1)
                time.sleep(0.5)
                lgpio.gpio_write(h, PIN_HORN, 0)
                time.sleep(0.5)
            
            if reset_event.is_set():
                break

            for _ in range(10):  
                if reset_event.is_set():
                    break
                time.sleep(0.1)
                
    finally:
        lgpio.gpio_write(h, PIN_HORN, 0)
        lgpio.gpiochip_close(h)
        strobe_active.clear()
        sense.clear()
        if os.path.exists(ALARM_LOCK_FILE):
            os.remove(ALARM_LOCK_FILE)
            
        with state_lock:
            alarm_active = False
            is_manual_drill = False
            
        print("Alarm successfully reset and cleared.")

class DrillHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global alarm_active, is_manual_drill
        if self.path == '/drill':
            threading.Thread(target=trigger_tier1_fire_emergency, args=("MANUAL DRILL TEST", True)).start()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"on")
        elif self.path == '/reset':
            with state_lock:
                can_reset = is_manual_drill and alarm_active
                
            if can_reset:
                print("Web reset received: Clearing active drill.")
                with state_lock:
                    alarm_active = False
                    is_manual_drill = False
                reset_event.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"off")
            else:
                print("⚠️ Web reset rejected: Real fire alarm active or no drill running!")
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"locked")
        elif self.path == '/status':
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            with state_lock:
                status_val = b"on" if alarm_active else b"off"
            self.wfile.write(status_val)
        else:
            self.send_response(404)
            self.end_headers()

def http_server_loop():
    server = HTTPServer(('127.0.0.1', 9993), DrillHandler)
    server.serve_forever()

def trigger_secondary_alarm(reason):
    """Trigger the secondary alarm with the specific fault reason passed as an argument."""
    print(f"⚠️ Secondary Alarm Triggered: {reason}")
    try:
        # Pass the reason argument directly to the secondary script
        subprocess.Popen(
            ["python3", "/home/pi/alarms/urgent_march_alarm.py", reason], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"Failed to start secondary alarm script: {e}")

def monitor_loop():
    print("Fire monitoring daemon active...")
    last_fault_state = None
    
    while True:
        try:
            temp = sense.get_temperature()
            if temp >= SENSE_TEMP_THRESHOLD:
                trigger_tier1_fire_emergency(f"SENSE HAT OVERHEAT ({temp}C)", manual=False)

            resp = requests.get("http://127.0.0.1:7125/printer/info", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json().get('result', {})
                state = data.get('state', '')
                message = data.get('state_message', '').lower()
                
                if state in ['error', 'shutdown']:
                    # Only alert if this is a new/different fault message
                    if last_fault_state != message:
                        thermal_keywords = [
                            'thermal runaway', 
                            'not heating at expected rate', 
                            'exceeded max temp',
                            'heater', 
                            'adc out of range',
                            'min_temp',
                            'max_temp'
                        ]
                        
                        if any(kw in message for kw in thermal_keywords):
                            trigger_tier1_fire_emergency(f"THERMAL CRITICAL: {message.upper()}", manual=False)
                        else:
                            trigger_secondary_alarm(message.upper())
                            
                        last_fault_state = message
                else:
                    # Reset the latch once Klipper is fully back to ready
                    if state == 'ready':
                        last_fault_state = None
                        
        except Exception as e:
            print(f"Monitor loop error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=joystick_listener_thread, daemon=True).start()
    threading.Thread(target=http_server_loop, daemon=True).start()
    threading.Thread(target=strobe_worker, daemon=True).start()
    monitor_loop()
