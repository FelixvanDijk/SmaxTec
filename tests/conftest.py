"""An offline HTTP stand-in for the login flow. No live credentials or site calls."""

import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


@dataclass
class Website:
    origin: str = ""
    mode: str = "success"
    submissions: int = 0


@pytest.fixture
def website():
    site = Website()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def html(self, body):
            content = f"<!doctype html><html><body>{body}</body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def redirect(self, destination):
            self.send_response(303)
            self.send_header("Location", destination)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path == "/login":
                if site.mode == "changed":
                    self.html("<h1>New sign-in page</h1>")
                else:
                    self.html("<button onclick=\"location.href='/auth'\">Go to log in</button>")
            elif self.path == "/auth":
                destination = (
                    "https://unexpected.example.test/submit"
                    if site.mode == "untrusted-form"
                    else "/submit"
                )
                self.html(
                    f'<form method="post" action="{destination}">'
                    '<input id="username" name="username" autocomplete="username">'
                    '<input id="password" name="password" type="password">'
                    '<input id="kc-login" type="submit" value="Sign In"></form>'
                )
            elif self.path == "/rejected":
                self.html('<span id="input-error">Invalid account details</span>')
            elif self.path == "/challenge":
                self.html(
                    '<form method="post" action="/verify">'
                    '<input name="otp" autocomplete="one-time-code">'
                    '<button type="submit">Verify</button></form>'
                )
            elif self.path == "/home":
                self.html(
                    "<h1>Public page only</h1>"
                    if site.mode == "false-success"
                    else '<header data-testid="navigationHeader">Workspace</header>'
                    '<nav data-testid="menuItems">Navigation</nav>'
                )
            else:
                self.html("<h1>Not found</h1>")

        def do_POST(self):
            content = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            fields = parse_qs(content)
            if self.path == "/verify":
                self.redirect("/home")
                return
            site.submissions += 1
            valid = fields == {
                "username": ["analyst@example.test"],
                "password": ["synthetic-password"],
            }
            if not valid or site.mode == "reject":
                self.redirect("/rejected")
            elif site.mode == "challenge":
                self.redirect("/challenge")
            else:
                self.redirect("/home")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    site.origin = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
