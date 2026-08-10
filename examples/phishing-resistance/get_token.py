#!/usr/bin/env python3
"""Interactive Entra login -> v1.0 id_token (with amr) for the MACAW phishing-resistance demo.

Fill in the CONFIG below (or set ENTRA_TENANT_ID / ENTRA_CLIENT_ID). Run it, then sign in
in the browser that opens:

  - PASSKEY  (Touch ID / security key)  -> amr:["fido"]      -> phishing-resistant  (ALLOW run)
  - PASSWORD                            -> amr:["pwd","mfa"] -> not                 (DENY run)

It stores the token to ~/.macaw_demo_token (0600) and prints the export line the example reads.

Notes:
  - Uses Entra's v1.0 endpoint (/oauth2/authorize) because only v1.0 id_tokens carry `amr`.
  - Implicit flow (response_type=id_token) -> no client secret needed.
  - Standalone: Python stdlib only, imports nothing from the client. No wheel/Nuitka build.

One-time Entra setup: App registration -> Authentication -> add redirect URI
  http://localhost:8400  (Web platform), and ensure "ID tokens (implicit)" is enabled.
"""
import os
import sys
import json
import base64
import secrets
import threading
import webbrowser
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---- CONFIG (edit these, or set the env vars) ------------------------------
# Your Entra app registration's directory (tenant) ID and application (client) ID.
TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "YOUR_ENTRA_TENANT_ID")
CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "YOUR_ENTRA_CLIENT_ID")
PORT = 8400
# ----------------------------------------------------------------------------

REDIRECT = f"http://localhost:{PORT}"
TOKEN_FILE = os.path.expanduser("~/.macaw_demo_token")
AUTHORIZE = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/authorize"
PHISHING_RESISTANT_AMR = {"fido", "fido2", "hwk", "ngcmfa", "phr", "phrh"}

_result = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            # The id_token arrives in the URL fragment (#...), which browsers do not send to
            # the server. Serve a tiny page that bounces the fragment to /capture as a query.
            self._html("<script>location.replace('/capture?'+location.hash.substring(1))</script>")
        elif parsed.path == "/capture":
            _result.update({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()})
            self._html("<h3>Login complete — you can close this tab.</h3>")
        else:
            self.send_response(404)
            self.end_headers()

    def _html(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass  # quiet


def main():
    params = {
        "client_id": CLIENT_ID,
        "response_type": "id_token",
        "redirect_uri": REDIRECT,
        "scope": "openid",
        "nonce": secrets.token_urlsafe(8),
        "response_mode": "fragment",
        "prompt": "login",  # force a fresh login so you can choose passkey vs password
    }
    url = AUTHORIZE + "?" + urllib.parse.urlencode(params)

    server = HTTPServer(("localhost", PORT), Handler)
    print("Opening browser… sign in with a PASSKEY (phishing-resistant) or a PASSWORD (not).")
    webbrowser.open(url)

    # Serve requests until we capture the token (GET / then GET /capture).
    while "id_token" not in _result and "error" not in _result:
        server.handle_request()

    if "error" in _result:
        print(f"Login error: {_result.get('error')} — {_result.get('error_description', '')}")
        sys.exit(1)

    idt = _result["id_token"]
    with open(TOKEN_FILE, "w") as f:
        f.write(idt)
    os.chmod(TOKEN_FILE, 0o600)

    # Decode (unverified) just to tell you which run you'll get.
    payload = idt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    amr = claims.get("amr") or []
    resistant = any(str(m).lower() in PHISHING_RESISTANT_AMR for m in amr)

    print(f"\n  Signed in as {claims.get('upn') or claims.get('email')}")
    print(f"  amr = {amr}  ->  " +
          ("PHISHING-RESISTANT ✓  (ALLOW run)" if resistant
           else "not phishing-resistant  (DENY run)"))
    print(f"  token saved to {TOKEN_FILE}")
    print(f"\n  export ALICE_TOKEN=$(cat {TOKEN_FILE})\n")


if __name__ == "__main__":
    main()
