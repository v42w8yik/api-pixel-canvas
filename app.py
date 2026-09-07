"""Local-only pixel canvas with a small HTTP API and browser UI."""

from __future__ import annotations

import argparse
import json
import re
import struct
import threading
import zlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CANVAS_SIZE = 64
MAX_PIXELS_PER_REQUEST = 4096
MAX_REQUEST_BYTES = 512 * 1024
DEFAULT_COLOR = "#ffffff"
ALLOWED_ORIGINS = {"http://localhost:8000", "http://127.0.0.1:8000"}
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
STATIC_DIR = Path(__file__).with_name("web")


class Canvas:
    def __init__(self, size: int = CANVAS_SIZE, default_color: str = DEFAULT_COLOR):
        self.size = size
        self.default_color = default_color
        self._pixels = [default_color] * (size * size)
        self._version = 0
        self._lock = threading.RLock()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def set_pixels(self, pixels: list[dict[str, Any]]) -> int:
        validated = [validate_pixel(pixel, self.size) for pixel in pixels]
        with self._lock:
            for x, y, color in validated:
                self._pixels[y * self.size + x] = color.lower()
            if validated:
                self._version += 1
            return self._version

    def clear(self) -> int:
        with self._lock:
            self._pixels = [self.default_color] * (self.size * self.size)
            self._version += 1
            return self._version

    def snapshot(self) -> tuple[int, list[str]]:
        with self._lock:
            return self._version, self._pixels.copy()

    def png(self) -> bytes:
        _, pixels = self.snapshot()
        rgb = bytearray()
        for y in range(self.size):
            rgb.append(0)
            for color in pixels[y * self.size : (y + 1) * self.size]:
                rgb.extend(bytes.fromhex(color[1:]))
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", self.size, self.size, 8, 2, 0, 0, 0)
        return signature + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(rgb)) + png_chunk(b"IEND", b"")


def png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def validate_pixel(pixel: Any, size: int = CANVAS_SIZE) -> tuple[int, int, str]:
    if not isinstance(pixel, dict):
        raise ValueError("Each pixel must be a JSON object")
    x, y, color = pixel.get("x"), pixel.get("y"), pixel.get("color")
    if isinstance(x, bool) or not isinstance(x, int) or isinstance(y, bool) or not isinstance(y, int):
        raise ValueError("x and y must be integers")
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError(f"Coordinates must be between 0 and {size - 1}")
    if not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color):
        raise ValueError("color must use the #RRGGBB format")
    return x, y, color


class ApiHandler(BaseHTTPRequestHandler):
    canvas: Canvas

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/state":
            version, pixels = self.canvas.snapshot()
            self._json(HTTPStatus.OK, {"size": self.canvas.size, "version": version, "pixels": pixels})
        elif path == "/image":
            data = self.canvas.png()
            self.send_response(HTTPStatus.OK)
            self._cors_headers()
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", 'attachment; filename="pixel-canvas.png"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/pixel", "/pixels", "/clear"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            payload = self._read_json()
            if path == "/clear":
                version = self.canvas.clear()
                self._json(HTTPStatus.OK, {"ok": True, "version": version})
                return
            if path == "/pixel":
                version = self.canvas.set_pixels([payload])
                count = 1
            else:
                if not isinstance(payload, dict) or not isinstance(payload.get("pixels"), list):
                    raise ValueError("pixels must be an array")
                pixels = payload["pixels"]
                if len(pixels) > MAX_PIXELS_PER_REQUEST:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"At most {MAX_PIXELS_PER_REQUEST} pixels are allowed per request"})
                    return
                version = self.canvas.set_pixels(pixels)
                count = len(pixels)
            self._json(HTTPStatus.OK, {"ok": True, "updated": count, "version": version})
        except json.JSONDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON"})
        except ValueError as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})

    def _read_json(self) -> Any:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError(f"Request body must not exceed {MAX_REQUEST_BYTES} bytes")
        return json.loads(self.rfile.read(length))

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"API {self.address_string()} - {format % args}")


class UiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        filename = "index.html" if path == "/" else path.lstrip("/")
        if filename not in {"index.html", "app.js", "styles.css"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        file_path = STATIC_DIR / filename
        data = file_path.read_bytes()
        content_types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types[file_path.suffix])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def make_server(host: str, port: int, handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local pixel canvas UI and API")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--ui-port", type=int, default=8000)
    parser.add_argument("--api-port", type=int, default=8001)
    args = parser.parse_args()

    ApiHandler.canvas = Canvas()
    ui_server = make_server(args.host, args.ui_port, UiHandler)
    api_server = make_server(args.host, args.api_port, ApiHandler)
    ui_thread = threading.Thread(target=ui_server.serve_forever, daemon=True)
    ui_thread.start()
    print(f"Web UI: http://{args.host}:{args.ui_port}")
    print(f"API:    http://{args.host}:{args.api_port}")
    try:
        api_server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping servers...")
    finally:
        api_server.shutdown()
        ui_server.shutdown()
        ui_server.server_close()
        api_server.server_close()


if __name__ == "__main__":
    main()
