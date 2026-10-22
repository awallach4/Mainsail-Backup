import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from kasa import Discover
import os
import sys
import signal

sys.path.append("/usr/lib/python3/dist-packages")

from dotenv import load_dotenv

signal.signal(signal.SIGPIPE, signal.SIG_IGN)

env_path = '/home/pi/.env'

if not load_dotenv(dotenv_path=env_path):
    print(f"Error: Could not load environment file at {env_path}", file=sys.stderr)
    sys.exit(1)

HOST = os.getenv("KASA_IP")
USER = os.getenv("KASA_USERNAME")
PASS = os.getenv("KASA_PASSWORD")

PORT = 9991
ALARM_LOCK_FILE = '/tmp/fire_alarm_active.lock'

def get_plug_state():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        dev = loop.run_until_complete(Discover.discover_single(HOST, username=USER, password=PASS))
        loop.run_until_complete(dev.update())
        is_on = dev.is_on
        loop.close()
        return "on" if is_on else "off"
    except Exception as e:
        print(f"Error fetching state: {e}")
        return "off"

class KasaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        action = self.path.strip('/')
        if action in ['on', 'off']:
            # SAFETY INTERLOCK: Prevent turning ON if the fire alarm lock exists
            if action == 'on' and os.path.exists(ALARM_LOCK_FILE):
                print("⚠️ Interlock Blocked: Attempted to turn ON 24V power while Fire Alarm is active!")
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Blocked: Fire Alarm Active")
                return

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                dev = loop.run_until_complete(Discover.discover_single(HOST, username=USER, password=PASS))
                if action == 'off':
                    loop.run_until_complete(dev.turn_off())
                elif action == 'on':
                    loop.run_until_complete(dev.turn_on())
                loop.close()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(action.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif action == 'status':
            state = get_plug_state()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(state.encode())
        else:
            self.send_response(400)
            self.end_headers()

def run():
    server = HTTPServer(('127.0.0.1', PORT), KasaHandler)
    server.serve_forever()

if __name__ == '__main__':
    run()
