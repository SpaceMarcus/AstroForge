"""Installer-free desktop host for the bundled AstroForge Lite web application.

Only loopback is served. No Node/Python installation is required by the frozen
executable. The browser remains the UI; this small window owns server lifetime.
"""
from __future__ import annotations

import argparse
import errno
from functools import partial
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import socket
import sys
import threading
from urllib.parse import unquote, urlsplit
import webbrowser


def asset_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parents[1] / "dist"


class StaticHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def log_message(self, *_args):
        # Windowed PyInstaller has no stderr. Avoid console windows and logs.
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def list_directory(self, _path):
        self.send_error(403, "Directory listing disabled")
        return None

    def send_head(self):
        decoded = unquote(urlsplit(self.path).path)
        if "\x00" in decoded or "\\" in decoded or ".." in PurePosixPath(decoded).parts:
            self.send_error(403, "Invalid asset path")
            return None
        root = Path(self.directory).resolve()
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(root):
            self.send_error(403, "Asset outside application directory")
            return None
        return super().send_head()


class LoopbackHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR would allow another server to bind the same port.
    # Exclusive binding makes the fallback deterministic and avoids ambiguity.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def start_server(root: Path, port: int = 4174):
    if not (root / "index.html").is_file() or not (root / "thermo.json").is_file():
        raise RuntimeError("Die gebündelten Web-Dateien fehlen. Bitte den Lite-Build erneut erstellen.")
    handler = partial(StaticHandler, directory=str(root))
    try:
        server = LoopbackHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        if port == 0 or exc.errno not in {errno.EADDRINUSE, errno.EACCES, 10048, 10013}:
            raise
        # Never terminate the process using the preferred port.
        server = LoopbackHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="AstroForge-localhost", daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def smoke_test(server):
    host, port = server.server_address
    checks = []
    for path in ["/", "/src/app.js", "/src/worker.js", "/thermo.json", "/manifest.webmanifest"]:
        connection = http.client.HTTPConnection(host, port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
            if response.status != 200 or not body:
                raise RuntimeError(f"Asset smoke test failed: {path} ({response.status})")
            if path == "/" and b"AstroForge" not in body:
                raise RuntimeError("Unexpected index.html")
            if path == "/thermo.json" and json.loads(body).get("format") != "astroforge-thermo-grid":
                raise RuntimeError("Unexpected thermochemistry data")
            checks.append(path)
        finally:
            connection.close()
    for path in ["/%2e%2e/package.json", "/src/", "/%5c..%5cpackage.json"]:
        connection = http.client.HTTPConnection(host, port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            response.read()
            if response.status != 403:
                raise RuntimeError(f"Asset confinement failed: {path} ({response.status})")
        finally:
            connection.close()
    alternate, alternate_thread = start_server(asset_root(), port)
    try:
        if alternate.server_port == port:
            raise RuntimeError("Occupied-port fallback failed")
    finally:
        stop_server(alternate, alternate_thread)
    if sys.stdout:
        print(json.dumps({"status": "passed", "bind": host, "assets": checks, "path_confinement": "passed"}))


def show_window(url: str, fallback_port: bool):
    import tkinter as tk
    from tkinter import messagebox

    window = tk.Tk()
    window.title("AstroForge 2.0 Lite")
    window.geometry("540x330")
    window.minsize(500, 320)
    window.configure(bg="#111619")
    fg, muted, accent = "#edf0ee", "#a2aeac", "#eeb564"
    main = tk.Frame(window, bg="#111619", padx=28, pady=24)
    main.pack(fill="both", expand=True)
    tk.Label(main, text="ASTROFORGE  2.0 LITE", font=("Segoe UI", 19, "bold"), fg=fg, bg="#111619").pack(anchor="w")
    tk.Label(main, text="Lokaler Arbeitsraum ist bereit", font=("Segoe UI", 11), fg=accent, bg="#111619", pady=12).pack(anchor="w")
    address = tk.Entry(main, font=("Consolas", 11), readonlybackground="#1c252a", fg=fg, relief="flat")
    address.insert(0, url)
    address.configure(state="readonly")
    address.pack(fill="x", ipady=9)
    status = tk.StringVar(value="Dieses Fenster geöffnet lassen, solange du mit Lite arbeitest.")
    tk.Label(main, textvariable=status, font=("Segoe UI", 10), fg=muted, bg="#111619", wraplength=475, justify="left", pady=12).pack(anchor="w")
    note = ("Port 4174 ist belegt: alternative lokale Adresse.\nBrowser-Autosave ist hier getrennt; Projektdatei speichern/öffnen."
            if fallback_port else "Feste lokale Adresse für Browser-Autosave.\nFür Gerätewechsel oder Sicherung: Projekt als Datei speichern.")
    tk.Label(main, text=note, font=("Segoe UI", 10), fg=accent if fallback_port else muted, bg="#111619", justify="left", wraplength=475).pack(anchor="w")
    actions = tk.Frame(main, bg="#111619", pady=18)
    actions.pack(fill="x")

    def open_browser():
        try:
            opened = webbrowser.open(url, new=2)
            status.set("AstroForge wurde im Standardbrowser geöffnet." if opened else "Bitte die Adresse kopieren und im Browser öffnen.")
        except Exception:
            status.set("Bitte die Adresse kopieren und im Browser öffnen.")

    def copy_url():
        window.clipboard_clear()
        window.clipboard_append(url)
        status.set("Adresse kopiert. Nur auf diesem Windows-Gerät erreichbar.")

    def close():
        if messagebox.askokcancel("AstroForge beenden", "Der lokale Server wird beendet. Ist dein Projekt als Datei gespeichert?", parent=window):
            window.destroy()

    for label, command, primary in [("Im Browser öffnen", open_browser, True), ("Adresse kopieren", copy_url, False), ("Beenden", close, False)]:
        tk.Button(actions, text=label, command=command, bg=accent if primary else "#273238", fg="#111619" if primary else fg, activebackground="#dca454" if primary else "#35434b", relief="flat", padx=12, pady=8, font=("Segoe UI", 10), cursor="hand2").pack(side="left", padx=(0,8))
    window.protocol("WM_DELETE_WINDOW", close)
    window.after(250, open_browser)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description="AstroForge 2.0 Lite local desktop host")
    parser.add_argument("--smoke-test", action="store_true", help="Verify bundled assets and exit without a browser or window")
    args = parser.parse_args()
    server = thread = None
    try:
        server, thread = start_server(asset_root(), port=0 if args.smoke_test else 4174)
        if args.smoke_test:
            smoke_test(server)
        else:
            show_window(f"http://127.0.0.1:{server.server_port}/", server.server_port != 4174)
        return 0
    except Exception as exc:
        if sys.stderr:
            print(str(exc), file=sys.stderr)
        if not args.smoke_test:
            from tkinter import messagebox
            messagebox.showerror("AstroForge konnte nicht starten", str(exc))
        return 1
    finally:
        if server:
            stop_server(server, thread)


if __name__ == "__main__":
    raise SystemExit(main())
