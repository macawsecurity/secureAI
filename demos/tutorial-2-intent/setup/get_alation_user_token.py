#!/usr/bin/env python3
"""
get_alation_user_token.py -- one-shot Alation USER token via OAuth authorization_code + PKCE.

Runs the interactive (User-Initiated) OAuth flow: opens a browser to Alation's authorize
endpoint, catches the redirect on a local callback server, and exchanges the code (+ PKCE
verifier) for an access_token + refresh_token that act AS the logged-in user. Prints an
`export ALATION_TOKEN=...` line you paste into the proxy env.

Prereqs: an Alation "User-Initiated OAuth Client" (Confidential, PKCE) whose Redirect URI is
EXACTLY the one below (default http://127.0.0.1:18722/callback).

Env / config:
    ALATION_BASE_URL        (required)  e.g. https://macaw.mtse.alationcloud.com
    ALATION_CLIENT_ID       (required)
    ALATION_CLIENT_SECRET   (required for Confidential clients; omit for Public)
    ALATION_REDIRECT_URI    (default http://127.0.0.1:18722/callback  -- MUST match the client)
    ALATION_SCOPE           (optional, space-delimited)
    ALATION_AUTHORIZE_PATH  (default /oauth/v1/authorize)
    ALATION_TOKEN_PATH      (default /oauth/v2/token/)

Run:
    export ALATION_BASE_URL="https://macaw.mtse.alationcloud.com"
    export ALATION_CLIENT_ID="..."
    export ALATION_CLIENT_SECRET="..."
    python get_alation_user_token.py            # opens the browser, then prints the token
    python get_alation_user_token.py --refresh <REFRESH_TOKEN>   # renew without logging in again
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

BASE = os.environ.get("ALATION_BASE_URL", "").rstrip("/")
CLIENT_ID = os.environ.get("ALATION_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ALATION_CLIENT_SECRET", "")
REDIRECT = os.environ.get("ALATION_REDIRECT_URI", "http://127.0.0.1:18722/callback")
SCOPE = os.environ.get("ALATION_SCOPE", "")
AUTHORIZE_PATH = os.environ.get("ALATION_AUTHORIZE_PATH", "/oauth/v1/authorize")
# authorization_code exchange is on the v1 family (v2/token is client_credentials-only,
# it returns unsupported_grant_type). Override with ALATION_TOKEN_PATH if your instance differs.
TOKEN_PATH = os.environ.get("ALATION_TOKEN_PATH", "/oauth/v1/token")


def _post_token(data: dict) -> dict:
    url = BASE + TOKEN_PATH
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req) as r:  # noqa: S310 (trusted Alation host)
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        sys.exit(
            f"\nToken exchange FAILED: POST {url} -> HTTP {e.code}\n"
            f"  response: {detail}\n"
            f"  hint: if this says unsupported_grant_type / invalid endpoint, set "
            f"ALATION_TOKEN_PATH=/oauth/v1/token (match the v1 authorize) and re-run "
            f"(a NEW browser login -- the auth code is single-use)."
        )


def _print_tokens(tok: dict) -> None:
    at = tok.get("access_token")
    rt = tok.get("refresh_token")
    if not at:
        sys.exit(f"No access_token in response: {tok}")
    print("\n" + "=" * 64)
    print("Alation USER access token (acts as the logged-in user):\n")
    print(f'export ALATION_TOKEN="{at}"')
    if rt:
        print(f'\n# refresh token (renew later): {rt}')
    print("=" * 64)


def refresh(refresh_token: str) -> None:
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": CLIENT_ID}
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET
    _print_tokens(_post_token(data))


def login() -> None:
    # PKCE
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)

    q = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if SCOPE:
        q["scope"] = SCOPE
    authorize_url = f"{BASE}{AUTHORIZE_PATH}?{urllib.parse.urlencode(q)}"

    caught = {}
    parsed = urllib.parse.urlparse(REDIRECT)
    host, port, path = parsed.hostname, parsed.port or 80, parsed.path

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != path:
                self.send_response(404); self.end_headers(); return
            params = urllib.parse.parse_qs(u.query)
            caught["code"] = (params.get("code") or [None])[0]
            caught["state"] = (params.get("state") or [None])[0]
            caught["error"] = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h3>Alation login complete - you can close this tab.</h3>")

        def log_message(self, *_):  # silence
            pass

    srv = http.server.HTTPServer((host, port), Handler)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    print(f"Opening browser for Alation login...\n  {authorize_url}\n", file=sys.stderr)
    try:
        webbrowser.open(authorize_url)
    except Exception:
        pass
    print("If no browser opened, paste the URL above into one.", file=sys.stderr)

    # wait for the single callback
    import time
    for _ in range(600):  # ~5 min
        if caught:
            break
        time.sleep(0.5)
    if not caught:
        sys.exit("Timed out waiting for the OAuth callback.")
    if caught.get("error"):
        sys.exit(f"Authorization error: {caught['error']}")
    if caught.get("state") != state:
        sys.exit("State mismatch (possible CSRF) -- aborting.")
    code = caught.get("code")
    if not code:
        sys.exit("No authorization code received.")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": CLIENT_ID,
        "code_verifier": verifier,
    }
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET
    _print_tokens(_post_token(data))


if __name__ == "__main__":
    if not BASE or not CLIENT_ID:
        sys.exit("Set ALATION_BASE_URL and ALATION_CLIENT_ID (see the module docstring).")
    if len(sys.argv) == 3 and sys.argv[1] == "--refresh":
        refresh(sys.argv[2])
    else:
        login()
