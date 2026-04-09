"""
Quick daily Kite re-login.
Run this every morning before market opens.
Opens browser, you log in, token auto-saved.
Usage: python3 scripts/kite_daily_login.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import webbrowser
from app.data.kite_client import get_login_url, complete_login

class CallbackHandler(BaseHTTPRequestHandler):
    request_token = None
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        token = params.get("request_token", [None])[0]
        if token:
            CallbackHandler.request_token = token
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:sans-serif;text-align:center;padding:80px;background:#f0fff4'>
                <h1 style='color:#276749'>Login successful!</h1>
                <p style='font-size:18px'>Token saved. You can close this tab.</p>
                <p style='color:#666'>Trading Assistant is ready for today.</p>
                </body></html>
            """)
    def log_message(self, *args): pass

def main():
    print("\n" + "="*50)
    print("  KITE DAILY LOGIN")
    print("="*50)
    print("Opening browser for Zerodha login...")
    webbrowser.open(get_login_url())
    print("Waiting for login...")
    server = HTTPServer(("127.0.0.1", 5000), CallbackHandler)
    while CallbackHandler.request_token is None:
        server.handle_request()
    token = complete_login(CallbackHandler.request_token)
    print("\n✅ Login successful!")
    print("✅ Token saved for today")
    from app.data.kite_client import get_profile
    p = get_profile()
    print(f"✅ Account: {p.get('user_name')} ({p.get('user_id')})")
    print(f"✅ Broker: {p.get('broker')}")
    print("\nYou can now run the bot. Have a good trading day!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
