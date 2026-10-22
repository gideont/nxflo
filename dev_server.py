#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import os
import posixpath
import socketserver
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lib.site import render_page
from lib.seo import crawl_assets


WATCH_EXTENSIONS = {".html", ".css", ".js", ".py", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
POLL_INTERVAL_SECONDS = 0.5
HOT_RELOAD_PATH = "/__hot_reload__"


def build_reload_snippet() -> bytes:
    script = """
<script>
(() => {
    const retryDelayMs = 1000;

    const connect = () => {
        const source = new EventSource("/__hot_reload__");

        source.addEventListener("reload", () => {
            source.close();
            window.location.reload();
        });

        source.onerror = () => {
            source.close();
            window.setTimeout(connect, retryDelayMs);
        };
    };

    connect();
})();
</script>
"""
    return script.encode("utf-8")


RELOAD_SNIPPET = build_reload_snippet()


class HotReloadState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._version = 0
        self._lock = threading.Lock()
        self._snapshot = self._scan()

    def _scan(self) -> dict[str, int]:
        snapshot: dict[str, int] = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in WATCH_EXTENSIONS:
                continue
            try:
                snapshot[str(path.relative_to(self.root))] = path.stat().st_mtime_ns
            except FileNotFoundError:
                continue
        return snapshot

    def watch(self) -> None:
        while True:
            time.sleep(POLL_INTERVAL_SECONDS)
            current = self._scan()
            if current != self._snapshot:
                with self._lock:
                    self._version += 1
                    self._snapshot = current

    def current_version(self) -> int:
        with self._lock:
            return self._version


class HotReloadHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, reload_state: HotReloadState, **kwargs) -> None:
        self.reload_state = reload_state
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        asset_name = urlsplit(self.path).path.lstrip("/")
        assets = crawl_assets()
        if asset_name in assets:
            content = assets[asset_name].encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/xml; charset=utf-8" if asset_name.endswith(".xml") else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == HOT_RELOAD_PATH:
            self.serve_hot_reload_stream()
            return

        if self.is_html_request():
            self.serve_html_with_reload()
            return

        super().do_GET()

    def is_html_request(self) -> bool:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/" or path.endswith(".html"):
            return True
        return False

    def serve_hot_reload_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_version = self.reload_state.current_version()

        try:
            while True:
                current_version = self.reload_state.current_version()
                if current_version != last_version:
                    self.wfile.write(b"event: reload\ndata: now\n\n")
                    self.wfile.flush()
                    return

                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                time.sleep(POLL_INTERVAL_SECONDS)
        except (BrokenPipeError, ConnectionResetError):
            return

    def serve_html_with_reload(self) -> None:
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            for index in ("index.html", "index.htm"):
                candidate = os.path.join(path, index)
                if os.path.exists(candidate):
                    path = candidate
                    break
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return

        if not os.path.exists(path):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        try:
            content = render_page(
                Path(path).read_text(encoding="utf-8"), Path(path).name, Path(self.directory)
            ).encode("utf-8")
        except (ValueError, OSError) as error:
            self.log_error("Page render failed: %s", error)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Page render failed")
            return

        if b"</body>" in content:
            content = content.replace(b"</body>", RELOAD_SNIPPET + b"\n</body>", 1)
        else:
            content += RELOAD_SNIPPET

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def translate_path(self, path: str) -> str:
        path = urlsplit(path).path
        path = posixpath.normpath(unquote(path))
        words = [segment for segment in path.split("/") if segment]
        translated = self.directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            translated = os.path.join(translated, word)
        return translated

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Static dev server with hot reload.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--dir", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.dir).resolve()
    reload_state = HotReloadState(root)

    watcher = threading.Thread(target=reload_state.watch, daemon=True)
    watcher.start()

    handler = lambda *handler_args, **handler_kwargs: HotReloadHandler(
        *handler_args,
        directory=str(root),
        reload_state=reload_state,
        **handler_kwargs,
    )

    with ThreadingTCPServer((args.host, args.port), handler) as httpd:
        print(f"Serving hot-reload preview on http://{args.host}:{args.port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping preview server.")


if __name__ == "__main__":
    main()
