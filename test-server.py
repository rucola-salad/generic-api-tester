#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import logging
import mimetypes
import ssl
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
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
    "open_browser": True,
    "logging": {
        "file_enabled": True,
        "file_level": "INFO",
        "console_enabled": False,
        "console_level": "INFO",
        "file": "logs/api-tester.log",
        "rotation": "size",
        "date_suffix_format": "%Y-%m-%d",
        "max_bytes": 5242880,
        "backup_count": 5,
        "request_headers": True,
        "request_body": True,
        "response_headers": True,
        "response_body": True,
        "max_body_length": 10000
    },
    "access_logging": {
        "enabled": True,
        "file": "logs/access.log",
        "rotation": "daily",
        "date_suffix_format": "%Y-%m-%d",
        "max_bytes": 5242880,
        "backup_count": 30
    }
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

LOG_CONFIG = CONFIG.get("logging", {})
LOG_FILE_ENABLED = bool(
    LOG_CONFIG.get("file_enabled", LOG_CONFIG.get("enabled", True))
)
LOG_FILE_LEVEL = str(
    LOG_CONFIG.get("file_level", "INFO")
).upper()
LOG_CONSOLE_ENABLED = bool(
    LOG_CONFIG.get("console_enabled", False)
)
LOG_CONSOLE_LEVEL = str(
    LOG_CONFIG.get("console_level", "INFO")
).upper()
LOG_FILE = str(LOG_CONFIG.get("file", "logs/api-tester.log"))
LOG_ROTATION = str(LOG_CONFIG.get("rotation", "size")).lower()
LOG_DATE_SUFFIX_FORMAT = str(
    LOG_CONFIG.get("date_suffix_format", "%Y-%m-%d")
)
LOG_MAX_BYTES = int(LOG_CONFIG.get("max_bytes", 5 * 1024 * 1024))
LOG_BACKUP_COUNT = int(LOG_CONFIG.get("backup_count", 5))
LOG_REQUEST_HEADERS = bool(LOG_CONFIG.get("request_headers", True))
LOG_REQUEST_BODY = bool(LOG_CONFIG.get("request_body", True))
LOG_RESPONSE_HEADERS = bool(LOG_CONFIG.get("response_headers", True))
LOG_RESPONSE_BODY = bool(LOG_CONFIG.get("response_body", True))
LOG_MAX_BODY_LENGTH = int(LOG_CONFIG.get("max_body_length", 10000))

ACCESS_LOG_CONFIG = CONFIG.get("access_logging", {})
ACCESS_LOG_ENABLED = bool(ACCESS_LOG_CONFIG.get("enabled", True))
ACCESS_LOG_FILE = str(
    ACCESS_LOG_CONFIG.get("file", "logs/access.log")
)
ACCESS_LOG_ROTATION = str(
    ACCESS_LOG_CONFIG.get("rotation", "daily")
).lower()
ACCESS_LOG_DATE_SUFFIX_FORMAT = str(
    ACCESS_LOG_CONFIG.get("date_suffix_format", "%Y-%m-%d")
)
ACCESS_LOG_MAX_BYTES = int(
    ACCESS_LOG_CONFIG.get("max_bytes", 5 * 1024 * 1024)
)
ACCESS_LOG_BACKUP_COUNT = int(
    ACCESS_LOG_CONFIG.get("backup_count", 30)
)

SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "apikey",
    "x-auth-token",
    "cookie",
    "set-cookie",
}


def _masked_headers(headers) -> dict:
    result = {}
    for key, value in dict(headers or {}).items():
        name = str(key)
        result[name] = (
            "********"
            if name.lower() in SENSITIVE_HEADERS
            else str(value)
        )
    return result


def _body_for_log(data, content_type: str = "") -> str:
    if data is None:
        return ""

    raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else bytes(data)
    ctype = (content_type or "").lower()
    is_text = (
        ctype.startswith("text/")
        or "json" in ctype
        or "xml" in ctype
        or "javascript" in ctype
        or "x-www-form-urlencoded" in ctype
    )

    if not is_text:
        return f"<binary {len(raw)} bytes>"

    text = raw.decode("utf-8", errors="replace")
    if len(text) > LOG_MAX_BODY_LENGTH:
        return (
            text[:LOG_MAX_BODY_LENGTH]
            + f"... <truncated, total {len(text)} chars>"
        )
    return text


class ConfigurableDailyRotatingFileHandler(TimedRotatingFileHandler):
    """Daily rotation with a configurable strftime suffix and retention."""

    def __init__(self, *args, date_suffix_format="%Y-%m-%d", **kwargs):
        self.date_suffix_format = date_suffix_format
        super().__init__(*args, **kwargs)
        self.suffix = date_suffix_format

    def getFilesToDelete(self):
        if self.backupCount <= 0:
            return []

        base_path = Path(self.baseFilename)
        candidates = [
            p for p in base_path.parent.glob(base_path.name + ".*")
            if p.is_file()
        ]
        candidates.sort(key=lambda p: (p.stat().st_mtime, p.name))

        if len(candidates) <= self.backupCount:
            return []
        return [str(p) for p in candidates[:-self.backupCount]]


def _validate_date_suffix_format(value: str) -> str:
    if not value:
        raise RuntimeError(
            "logging.date_suffix_format は空文字にできません"
        )
    if "/" in value or "\\" in value:
        raise RuntimeError(
            "logging.date_suffix_format にパス区切り文字は使用できません"
        )
    return value


def _create_rotating_handler(
    log_path: Path,
    rotation: str,
    max_bytes: int,
    backup_count: int,
    date_suffix_format: str,
    setting_name: str,
):
    if rotation == "daily":
        handler = ConfigurableDailyRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=max(0, backup_count),
            encoding="utf-8",
            utc=False,
            date_suffix_format=_validate_date_suffix_format(
                date_suffix_format
            ),
        )
    elif rotation == "size":
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max(1, max_bytes),
            backupCount=max(0, backup_count),
            encoding="utf-8",
        )
    else:
        raise RuntimeError(
            f"{setting_name}.rotation は 'size' または 'daily' を指定してください"
        )
    return handler


def _parse_log_level(value: str, setting_name: str) -> int:
    level = getattr(logging, str(value).upper(), None)
    if not isinstance(level, int):
        raise RuntimeError(
            f"{setting_name} は DEBUG / INFO / WARNING / ERROR / CRITICAL を指定してください"
        )
    return level


def _create_app_logger():
    logger = logging.getLogger("generic-api-tester-app")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    if LOG_FILE_ENABLED:
        log_path = Path(LOG_FILE)
        if not log_path.is_absolute():
            log_path = SCRIPT_DIR / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = _create_rotating_handler(
            log_path,
            LOG_ROTATION,
            LOG_MAX_BYTES,
            LOG_BACKUP_COUNT,
            LOG_DATE_SUFFIX_FORMAT,
            "logging",
        )
        file_handler.setLevel(
            _parse_log_level(LOG_FILE_LEVEL, "logging.file_level")
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"
            )
        )
        logger.addHandler(file_handler)

    if LOG_CONSOLE_ENABLED:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(
            _parse_log_level(
                LOG_CONSOLE_LEVEL,
                "logging.console_level",
            )
        )
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s"
            )
        )
        logger.addHandler(console_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    return logger


APP_LOGGER = _create_app_logger()



def _create_access_logger():
    logger = logging.getLogger("generic-api-tester-access")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    if not ACCESS_LOG_ENABLED:
        logger.addHandler(logging.NullHandler())
        return logger

    log_path = Path(ACCESS_LOG_FILE)
    if not log_path.is_absolute():
        log_path = SCRIPT_DIR / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = _create_rotating_handler(
        log_path,
        ACCESS_LOG_ROTATION,
        ACCESS_LOG_MAX_BYTES,
        ACCESS_LOG_BACKUP_COUNT,
        ACCESS_LOG_DATE_SUFFIX_FORMAT,
        "access_logging",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


ACCESS_LOGGER = _create_access_logger()


def _access_quote(value) -> str:
    text = "-" if value is None or value == "" else str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def log_access(
    client_ip: str,
    method: str,
    target_url: str,
    status: int,
    response_size: int,
    elapsed: float,
    user_agent: str,
) -> None:
    if not ACCESS_LOG_ENABLED:
        return

    stamp = time.strftime("%d/%b/%Y:%H:%M:%S %z")
    request_line = f"{method} {target_url}"
    line = (
        f"{client_ip or '-'} - - [{stamp}] "
        f"{_access_quote(request_line)} "
        f"{int(status)} {int(response_size)} "
        f"{elapsed * 1000.0:.1f}ms "
        f"{_access_quote(user_agent)}"
    )
    ACCESS_LOGGER.info(line)


def _content_type(headers) -> str:
    for key, value in dict(headers or {}).items():
        if str(key).lower() == "content-type":
            return str(value)
    return ""


def log_proxy_request(method: str, url: str, headers, body) -> None:
    if not (LOG_FILE_ENABLED or LOG_CONSOLE_ENABLED):
        return
    lines = [f"REQUEST {method} {url}"]
    if LOG_REQUEST_HEADERS:
        lines.append("Headers:")
        for name, value in _masked_headers(headers).items():
            lines.append(f"  {name}: {value}")
    if LOG_REQUEST_BODY:
        lines.append(
            "Body: " + _body_for_log(body, _content_type(headers))
        )
    APP_LOGGER.info("\n".join(lines))


def log_proxy_response(status, reason, elapsed: float, headers, body) -> None:
    if not (LOG_FILE_ENABLED or LOG_CONSOLE_ENABLED):
        return
    lines = [f"RESPONSE {status} {reason} ({elapsed:.3f} sec)"]
    if LOG_RESPONSE_HEADERS:
        lines.append("Headers:")
        for name, value in _masked_headers(headers).items():
            lines.append(f"  {name}: {value}")
    if LOG_RESPONSE_BODY:
        lines.append(
            "Body: " + _body_for_log(body, _content_type(headers))
        )
    APP_LOGGER.info("\n".join(lines))


def log_proxy_error(elapsed: float, exc: Exception) -> None:
    if LOG_FILE_ENABLED or LOG_CONSOLE_ENABLED:
        APP_LOGGER.error(
            "ERROR %s: %s (%.3f sec)",
            type(exc).__name__,
            exc,
            elapsed,
        )


def log(message: str, level: int = logging.INFO) -> None:
    APP_LOGGER.log(level, message)


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
        client_ip = (
            self.client_address[0]
            if self.client_address
            else "-"
        )
        user_agent = self.headers.get("User-Agent", "-")
        started = time.perf_counter()

        log_proxy_request(
            target_method,
            target_url,
            headers,
            body,
        )

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

                log_proxy_response(
                    response.status,
                    response.reason,
                    elapsed,
                    dict(response.headers.items()),
                    response_body,
                )

                log_access(
                    client_ip,
                    target_method,
                    target_url,
                    response.status,
                    len(response_body),
                    elapsed,
                    user_agent,
                )

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

            log_proxy_response(
                exc.code,
                exc.reason,
                elapsed,
                dict(exc.headers.items()) if exc.headers else {},
                response_body,
            )

            log_access(
                client_ip,
                target_method,
                target_url,
                exc.code,
                len(response_body),
                elapsed,
                user_agent,
            )

            log(f"[PROXY] HTTP {exc.code} {exc.reason}")
            log(f"[PROXY] Response: {len(response_body)} bytes")
            log(f"[PROXY] Elapsed : {elapsed:.3f} sec")

        except Exception as exc:
            elapsed = time.perf_counter() - started

            log_proxy_error(elapsed, exc)

            log_access(
                client_ip,
                target_method,
                target_url,
                502,
                0,
                elapsed,
                user_agent,
            )

            log("[PROXY] ERROR", logging.ERROR)
            print(f"[PROXY] Type    : {type(exc).__name__}")
            print(f"[PROXY] Message : {exc}")
            print(f"[PROXY] Elapsed : {elapsed:.3f} sec")

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

    print("")
    print("========================================")
    print("Generic API Tester")
    print("========================================")
    print(f"Web root : {WEB_ROOT}")
    print(f"URL      : http://localhost:{PORT}/")
    print(f"Proxy    : {PROXY_PATH}")
    print(f"Config   : {CONFIG_PATH}")
    print(f"Schemes  : {', '.join(sorted(ALLOWED_SCHEMES))}")
    print(f"Allowed  : {', '.join(sorted(ALLOWED_HOSTS))}")
    print(f"Browser  : {'open' if OPEN_BROWSER else 'disabled'}")
    print(f"Timeout  : {PROXY_TIMEOUT} sec")
    if LOG_FILE_ENABLED or LOG_CONSOLE_ENABLED:
        log_path = Path(LOG_FILE)
        if not log_path.is_absolute():
            log_path = SCRIPT_DIR / log_path
        print(f"Log file : {log_path}")
        print(f"Rotate   : {LOG_MAX_BYTES} bytes / {LOG_BACKUP_COUNT} backups")
    else:
        print("Log file : disabled")
    print("========================================")
    print("Press Ctrl+C to stop.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Stopping...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
