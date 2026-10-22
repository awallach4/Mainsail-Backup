#!/usr/init/env python3
import time
import subprocess
import os
from sense_hat import SenseHat

ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'
ALERT_LOCK_FILE = '/tmp/alert_alarm.lock'
sense = SenseHat()

def get_gateway_ip():
    # Automatically extract the default gateway IP from the routing table
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, check=True
        )
        # Output format usually contains "via <IP> dev ..."
        parts = result.stdout.split()
        if "via" in parts:
            return parts[parts.index("via") + 1]
    except Exception:
        pass
    return "192.168.1.1"  # Fallback standard gateway

def is_network_online(gateway):
    # Quick single ping with a 1-second timeout
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "1", gateway],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0

def monitor_loop():
    solid_blue = (0, 0, 255)
    gateway = get_gateway_ip()
    print(f"Network loss monitor active. Target gateway: {gateway}")
    
    while True:
        try:
            # SAFETY: Never override Tier 1 fire alarm
            if os.path.exists(ALARM_LOCK_FILE) or os.path.exists(ALERT_LOCK_FILE):
                time.sleep(2)
                continue
                
            if not is_network_online(gateway):
                # Network is down / Sonar is working to reconnect: Solid blue
                sense.clear(solid_blue)
            else:
                # Network is healthy: Clear auxiliary state
                sense.clear()
                
        except Exception as e:
            print(f"Network monitor error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    monitor_loop()
