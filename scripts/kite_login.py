"""
One-time Kite login script.
Run this once to authenticate. After that, token is saved and reused.

Usage:
    python3 scripts/kite_login.py
"""
import sys
import webbrowser
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from app.data.kite_client import get_login_url, complete_login, is_authenticated

class CallbackHandler(BaseHTTPRequestHandler):
    request_token = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("request_token", [None])[0]

        if token:
            CallbackHandler.request_token = token
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:sans-serif;text-align:center;padding:50px'>
                <h2>Login successful!</h2>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress server logs


def main():
    if is_authenticated():
        print("Already authenticated with Kite.")
        from app.data.kite_client import get_profile
        p = get_profile()
        print(f"Logged in as: {p.get('user_name')} ({p.get('user_id')})")
        return

    login_url = get_login_url()
    print(f"\nOpening Kite login in browser...")
    print(f"If browser doesn't open, go to:\n{login_url}\n")
    webbrowser.open(login_url)

    print("Waiting for login callback on http://127.0.0.1:5000/callback ...")
    server = HTTPServer(("127.0.0.1", 5000), CallbackHandler)

    while CallbackHandler.request_token is None:
        server.handle_request()

    print(f"\nGot request token. Generating access token...")
    token = complete_login(CallbackHandler.request_token)
    print(f"Login complete! Access token saved to data/kite_token.txt")

    from app.data.kite_client import get_profile
    p = get_profile()
    print(f"Logged in as: {p.get('user_name')} ({p.get('user_id')})")
    print(f"Broker: {p.get('broker')}")
    print(f"\nYou can now run the sync: python3 scripts/kite_sync.py")


if __name__ == "__main__":
    main()
