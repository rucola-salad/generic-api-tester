#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import mimetypes
import ssl
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "server-config.json"

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8000,
    "web_root": "html",
    "default_document": "api-tester.html",
    "proxy_path": "/proxy",
    "proxy_timeout": 60,
    "allowed_schemes": [
        "https"
    ],
    "allowed_hosts": [
        "jsonplaceholder.typicode.com",
        "httpbin.org"
    ],
    "open_browser": True
}


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)

    if CONFIG_PATH.is_file():
        try:
            loaded = json.loads(
                CONFIG_PATH.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise RuntimeError(
                f"server-config.json の読込に失敗しました: {exc}"
            ) from exc

        if not isinstance(loaded, dict):
            raise RuntimeError(
                "server-config.json のルートはJSONオブジェクトにしてください"
            )

        config.update(loaded)

    return config


CONFIG = load_config()

HOST = str(CONFIG["host"])
PORT = int(CONFIG["port"])

web_root_setting = str(CONFIG["web_root"])
WEB_ROOT = (
    Path(web_root_setting)
    if Path(web_root_setting).is_absolute()
    else SCRIPT_DIR / web_root_setting
)

DEFAULT_DOCUMENT = str(CONFIG["default_document"])
PROXY_PATH = str(CONFIG["proxy_path"])
PROXY_TIMEOUT = int(CONFIG["proxy_timeout"])

ALLOWED_SCHEMES = {
    str(value).lower()
    for value in CONFIG.get("allowed_schemes", ["https"])
}

ALLOWED_HOSTS = {
    str(value).lower()
    for value in CONFIG.get("allowed_hosts", [])
}

OPEN_BROWSER = bool(CONFIG.get("open_browser", True))


def log(message: str) -> None:
    print(message, flush=True)


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path

        if path == PROXY_PATH:
            self._proxy_request()
        elif path == "/readme":
            self._serve_readme()
        else:
            self._serve_static()

    def do_HEAD(self):
        if urlsplit(self.path).path == PROXY_PATH:
            self._proxy_request()
        else:
            super().do_HEAD()

    def do_POST(self):
        if urlsplit(self.path).path == PROXY_PATH:
            self._proxy_request()
        else:
            self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        if urlsplit(self.path).path == PROXY_PATH:
            self._proxy_request()
        else:
            self.send_error(404, "Not Found")


    def _serve_readme(self):
        readme_path = SCRIPT_DIR / "README.md"

        if not readme_path.is_file():
            self._send_json(404, {
                "error": "readme_not_found",
                "message": "README.md が見つかりません",
            })
            return

        data = readme_path.read_bytes()

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/markdown; charset=UTF-8",
        )
        self.send_header(
            "Content-Length",
            str(len(data)),
        )
        self.send_header(
            "Cache-Control",
            "no-store",
        )
        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(data)

    def _serve_static(self):
        if self.path in ("", "/"):
            self.path = "/" + DEFAULT_DOCUMENT
        log(f"[FILE ] {self.command} {self.path}")
        super().do_GET()

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()

        if self.command != "HEAD":
            self.wfile.write(data)

        self.close_connection = True

    def _proxy_request(self):
        target_url = self.headers.get("X-Proxy-Target", "").strip()
        target_method = self.headers.get("X-Proxy-Method", "GET").strip().upper()
        proxy_body_type = self.headers.get("X-Proxy-Body-Type", "").strip().lower()
        incoming_content_type = self.headers.get("Content-Type", "")

        if not target_url:
            self._send_json(400, {
                "error": "missing_proxy_target",
                "message": "X-Proxy-Target が指定されていません",
            })
            return

        parsed = urlsplit(target_url)

        scheme = (parsed.scheme or "").lower()

        if scheme not in ALLOWED_SCHEMES:
            self._send_json(403, {
                "error": "proxy_target_not_allowed",
                "message": (
                    "許可されていないURLスキームです: "
                    f"{scheme or '(なし)'}"
                ),
            })
            return

        hostname = (parsed.hostname or "").lower()

        if hostname not in ALLOWED_HOSTS:
            self._send_json(403, {
                "error": "proxy_target_not_allowed",
                "message": f"許可されていないホストです: {hostname}",
            })
            return

        try:
            upstream_headers = json.loads(
                self.headers.get("X-Proxy-Headers", "{}")
            )
        except Exception as exc:
            self._send_json(400, {
                "error": "invalid_proxy_headers",
                "message": str(exc),
            })
            return

        if not isinstance(upstream_headers, dict):
            self._send_json(400, {
                "error": "invalid_proxy_headers",
                "message": "X-Proxy-Headers はJSONオブジェクトで指定してください",
            })
            return

        body = None

        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        headers = {"Connection": "close"}

        if proxy_body_type == "multipart" and incoming_content_type:
            upstream_headers["Content-Type"] = incoming_content_type

        if proxy_body_type == "binary" and incoming_content_type:
            upstream_headers.setdefault("Content-Type", incoming_content_type)

        for key, value in upstream_headers.items():
            if value is not None:
                headers[str(key)] = str(value)

        request = urllib.request.Request(
            target_url,
            data=body,
            headers=headers,
            method=target_method,
        )

        context = ssl.create_default_context()
        started = time.perf_counter()

        log("")
        log("----------------------------------------")
        log(f"[PROXY] {target_method} {target_url}")

        if body is not None:
            log(f"[PROXY] Request body: {len(body)} bytes")

        try:
            with urllib.request.urlopen(
                request,
                timeout=PROXY_TIMEOUT,
                context=context,
            ) as response:

                response_body = response.read()

                self.send_response(
                    response.status,
                    response.reason,
                )

                content_type = response.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)

                location = response.headers.get("Location")
                if location:
                    self.send_header("Location", location)

                self.send_header(
                    "Content-Length",
                    str(len(response_body)),
                )
                self.send_header("Connection", "close")
                self.end_headers()

                if self.command != "HEAD" and response_body:
                    self.wfile.write(response_body)

                elapsed = time.perf_counter() - started

                log(f"[PROXY] HTTP {response.status} {response.reason}")
                log(f"[PROXY] Response: {len(response_body)} bytes")
                log(f"[PROXY] Elapsed : {elapsed:.3f} sec")

        except urllib.error.HTTPError as exc:
            response_body = exc.read()

            self.send_response(exc.code, exc.reason)

            content_type = exc.headers.get("Content-Type")
            if content_type:
                self.send_header("Content-Type", content_type)

            location = exc.headers.get("Location")
            if location:
                self.send_header("Location", location)

            self.send_header(
                "Content-Length",
                str(len(response_body)),
            )
            self.send_header("Connection", "close")
            self.end_headers()

            if self.command != "HEAD" and response_body:
                self.wfile.write(response_body)

            elapsed = time.perf_counter() - started

            log(f"[PROXY] HTTP {exc.code} {exc.reason}")
            log(f"[PROXY] Response: {len(response_body)} bytes")
            log(f"[PROXY] Elapsed : {elapsed:.3f} sec")

        except Exception as exc:
            elapsed = time.perf_counter() - started

            log("[PROXY] ERROR")
            log(f"[PROXY] Type    : {type(exc).__name__}")
            log(f"[PROXY] Message : {exc}")
            log(f"[PROXY] Elapsed : {elapsed:.3f} sec")

            self._send_json(502, {
                "error": "proxy_error",
                "target": target_url,
                "message": str(exc),
            })
            return

        finally:
            self.close_connection = True

    def log_message(self, fmt, *args):
        log(
            f"[HTTP ] {self.client_address[0]} - {fmt % args}"
        )


def main() -> int:
    if not WEB_ROOT.is_dir():
        print(
            f"HTML folder not found: {WEB_ROOT}",
            file=sys.stderr,
        )
        return 1

    mimetypes.add_type(
        "application/javascript",
        ".js",
    )
    mimetypes.add_type(
        "application/json",
        ".json",
    )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        Handler,
    )
    server.daemon_threads = True

    # 設定に応じて既定ブラウザを自動起動
    if OPEN_BROWSER:
        browser_host = (
            "localhost"
            if HOST in ("127.0.0.1", "0.0.0.0", "::")
            else HOST
        )

        webbrowser.open(
            f"http://{browser_host}:{PORT}/"
        )

    log("")
    log("========================================")
    log("Generic API Tester")
    log("========================================")
    log(f"Web root : {WEB_ROOT}")
    log(f"URL      : http://localhost:{PORT}/")
    log(f"Proxy    : {PROXY_PATH}")
    log(f"Config   : {CONFIG_PATH}")
    log(f"Schemes  : {', '.join(sorted(ALLOWED_SCHEMES))}")
    log(f"Allowed  : {', '.join(sorted(ALLOWED_HOSTS))}")
    log(f"Browser  : {'open' if OPEN_BROWSER else 'disabled'}")
    log(f"Timeout  : {PROXY_TIMEOUT} sec")
    log("========================================")
    log("Press Ctrl+C to stop.")
    log("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("")
        log("Stopping...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
