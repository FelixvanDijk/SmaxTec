"""An offline HTTP stand-in for the login flow. No live credentials or site calls."""

# ruff: noqa: E501

import json
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest

from smaxtec.adapters.smaxtec.login import LoginSettings, SmaxtecLoginSession

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")


@dataclass
class Website:
    origin: str = ""
    mode: str = "success"
    submissions: int = 0
    exports: list[dict[str, str]] | None = None

    def __post_init__(self):
        self.exports = []


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

        @staticmethod
        def shell(body, org_id="maes"):
            return (
                '<header data-testid="navigationHeader">Workspace</header>'
                '<nav data-testid="menuItems">Navigation</nav>'
                '<span data-testid="tooltip" aria-label="Change herd">'
                '<button type="button" onclick="document.querySelector(\'.farm-modal\').hidden=false">'
                '<svg data-testid="OrganisationSwitchIcon"></svg></button></span>'
                '<div class="farm-modal" hidden>'
                '<input data-testid="search-modal-input">'
                '<li data-testid="search-modal-list-item" '
                "onclick=\"location.href='/home?orgId=maes'\"><div><div>Maes Gwyrdd LTD</div></div><kbd>↵</kbd></li>"
                '<li data-testid="search-modal-list-item" '
                "onclick=\"location.href='/home?orgId=tyb'\"><div><div>TYB Farms LTD</div></div></li>"
                "</div>"
                f'<a href="/animals?orgId={org_id}"><i data-testid="sxicon-animals"></i>Animals</a>'
                f"{body}"
                '<script>document.addEventListener("keydown", e => {'
                'if(e.key === "Escape") document.querySelector(".farm-modal").hidden=true})</script>'
            )

        @staticmethod
        def animals(org_id):
            animals = ["57", "657", "257", "357"] if org_id == "maes" else ["12", "34"]
            if site.mode == "duplicate-cow":
                animals.append("57")
            data = json.dumps(animals)
            body = f"""
                <table>
                  <thead><tr data-testid="animalHeader">
                    <th><input data-testid="textInput" placeholder="Search"><span>Name</span></th>
                    <th><input id="animal-search" data-testid="textInput" placeholder="Search">
                        <span data-testid="orderByMark">Animal number</span></th>
                  </tr></thead>
                  <tbody id="rows"></tbody>
                </table>
                <div data-testid="animalFooter"></div>
                <div role="dialog" id="export-dialog" hidden>
                  <h2>EXPORT DATA</h2>
                  <div data-testid="datePicker"><input placeholder="DD/MM/YYYY" required></div>
                  <div data-testid="datePicker"><input placeholder="DD/MM/YYYY" required></div>
                  <label><input type="radio" name="kind" value="measured">Measured data</label>
                  <label><input type="radio" name="kind" value="messages" checked>Messages</label>
                  <button data-testid="close-icon" onclick="dialog.hidden=true">Close</button>
                  <button data-testid="button" id="final-export">EXPORT</button>
                  <div role="alert" id="export-error" hidden>Export failed</div>
                </div>
                <script>
                  const animals = {data};
                  const rows = document.getElementById('rows');
                  const footer = document.querySelector('[data-testid="animalFooter"]');
                  const dialog = document.getElementById('export-dialog');
                  const dateInputs = [...dialog.querySelectorAll('[data-testid="datePicker"] input')];
                  if ({str(site.mode == "mutate-start-date").lower()}) {{
                    dateInputs[0].addEventListener('blur', () => {{
                      dateInputs[0].value = dateInputs[0].value.replace(/2026$/, '2024');
                    }});
                  }}
                  let selectedCow = '';
                  function render(query = '') {{
                    const found = animals.filter(value => value.includes(query));
                    rows.innerHTML = found.map(value => `<tr data-testid="animalTable-row">
                      <td data-testid="name-link"><span data-testid="sxText">${{value}}</span></td>
                      <td data-testid="mark-link"><a><span data-testid="sxText">${{value}}</span></a></td>
                      <td><span data-testid="tooltip" aria-label="Export data">
                        <button data-testid="iconButton" data-cow="${{value}}">Export</button></span></td>
                    </tr>`).join('');
                    footer.textContent = found.length ? `1–${{found.length}} of ${{found.length}}` : '0–0 of 0';
                    document.querySelectorAll('[data-cow]').forEach(button => button.onclick = () => {{
                      selectedCow = button.dataset.cow; dialog.hidden = false;
                    }});
                  }}
                  document.getElementById('animal-search').addEventListener('input', e => render(e.target.value));
                  document.getElementById('final-export').onclick = async () => {{
                    const response = await fetch('/export', {{method:'POST', headers:{{'Content-Type':'application/json'}},
                      body:JSON.stringify({{farm:'{org_id}', cow:selectedCow, from:dateInputs[0].value,
                        to:dateInputs[1].value, kind:dialog.querySelector('[name=kind]:checked').value}})}});
                    if (response.ok) dialog.hidden = true;
                    else document.getElementById('export-error').hidden = false;
                  }};
                  render();
                </script>
            """
            return Handler.shell(body, org_id)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                if site.mode == "changed":
                    self.html("<h1>New sign-in page</h1>")
                else:
                    self.html("<button onclick=\"location.href='/auth'\">Go to log in</button>")
            elif parsed.path == "/auth":
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
            elif parsed.path == "/rejected":
                self.html('<span id="input-error">Invalid account details</span>')
            elif parsed.path == "/challenge":
                self.html(
                    '<form method="post" action="/verify">'
                    '<input name="otp" autocomplete="one-time-code">'
                    '<button type="submit">Verify</button></form>'
                )
            elif parsed.path == "/home":
                self.html(
                    "<h1>Public page only</h1>"
                    if site.mode == "false-success"
                    else self.shell(
                        "<main>Dashboard</main>",
                        parse_qs(parsed.query).get("orgId", ["maes"])[0],
                    )
                )
            elif parsed.path == "/animals":
                self.html(self.animals(parse_qs(parsed.query).get("orgId", ["maes"])[0]))
            else:
                self.html("<h1>Not found</h1>")

        def do_POST(self):
            content = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            if self.path == "/export":
                payload = json.loads(content)
                if site.mode == "export-reject" or (
                    site.mode == "reject-cow-257" and payload["cow"] == "257"
                ):
                    self.send_response(500)
                else:
                    site.exports.append(payload)
                    self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
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


@pytest.fixture
def session(website):
    adapter = SmaxtecLoginSession(
        LoginSettings(
            entry_url=f"{website.origin}/login",
            app_origin=website.origin,
            identity_origin=website.origin,
            headless=True,
            navigation_timeout_ms=5000,
            element_timeout_ms=1000,
            verification_timeout_ms=1200,
            challenge_timeout_ms=1200,
            export_confirmation_timeout_ms=1000,
        )
    )
    try:
        yield adapter
    finally:
        adapter.close()
