#!/usr/bin/env python3
import sys
import lgpio
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 9992
PIN_IR = 22

current_state = "off"
gpio_handle = None

def init_gpio():
    global gpio_handle
    try:
        gpio_handle = lgpio.gpiochip_open(0)
        # Claim pins as outputs defaulting to LOW (off for Active-HIGH)
        lgpio.gpio_claim_output(gpio_handle, PIN_IR, 0)
        print("GPIO initialized and pins claimed successfully.")
    except Exception as e:
        print(f"Initialization error: {e}", file=sys.stderr)
        sys.exit(1)

def set_lights(state: bool):
    global current_state, gpio_handle
    if gpio_handle is None:
        return False
    
    val = 1 if state else 0
    try:
        lgpio.gpio_write(gpio_handle, PIN_IR, val)
        current_state = "on" if state else "off"
        print(f"IR Floodlights {current_state.upper()} (Active-HIGH)")
        return True
    except Exception as e:
        print(f"Error writing to GPIO: {e}", file=sys.stderr)
        return False

class IRHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        action = self.path.strip('/')
        global current_state
        if action in ['on', 'off']:
            success = set_lights(action == 'on')
            if success:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(current_state.encode())
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"GPIO Write Error")
        elif action == 'status':
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(current_state.encode())
        else:
            self.send_response(400)
            self.end_headers()

def run():
    init_gpio()
    server = HTTPServer(('127.0.0.1', PORT), IRHandler)
    try:
        server.serve_forever()
    finally:
        if gpio_handle is not None:
            lgpio.gpiochip_close(gpio_handle)

if __name__ == '__main__':
    run()
