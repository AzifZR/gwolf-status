#!/usr/bin/env python3
"""
Gwolf Status Page — Ultra-Lightweight Monitoring Engine
Running on Termux Android (Port 3002)
Target: https://status.gwolfdev.my.id
"""

import time
import json
import socket
import urllib.request
import urllib.error
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 3002
BASE_DIR = Path.home() / "status-web"
STATIC_DIR = BASE_DIR / "static"
DATA_FILE = BASE_DIR / "data" / "history.json"

SERVICES = [
    {
        "id": "web_manager",
        "name": "Hermes Web Hub",
        "url": "http://127.0.0.1:8081",
        "public_url": "https://web.gwolfdev.my.id",
        "type": "http"
    },
    {
        "id": "dns_adguard",
        "name": "AdGuard Home DNS",
        "url": "http://127.0.0.1:3000",
        "public_url": "https://dns.gwolfdev.my.id",
        "type": "http"
    },
    {
        "id": "swiss_tools",
        "name": "Swiss Army Tools",
        "url": "http://127.0.0.1:8083",
        "public_url": "https://tools.gwolfdev.my.id",
        "type": "http"
    },
    {
        "id": "link_shortener",
        "name": "Bio-Link Kuliah",
        "url": "http://127.0.0.1:8082",
        "public_url": "https://link.gwolfdev.my.id",
        "type": "http"
    },
    {
        "id": "portway_space",
        "name": "Portway HF Space",
        "url": "https://gwolf20-gwolfdev.hf.space/api/v1/models/health",
        "public_url": "https://gwolf20-gwolfdev.hf.space",
        "type": "http"
    },
    {
        "id": "biznet_internet",
        "name": "Biznet Fiber Gateway",
        "host": "1.1.1.1",
        "port": 53,
        "public_url": "ISP: Biznet Home (CGNAT)",
        "type": "tcp"
    }
]

# In-memory history buffer (last 30 ticks per service)
# Each record: {"time": int, "status": "up"|"down", "ms": float}
history = {}

def load_history():
    global history
    if DATA_FILE.exists():
        try:
            history = json.loads(DATA_FILE.read_text())
        except Exception:
            history = {}
    for s in SERVICES:
        if s["id"] not in history:
            history[s["id"]] = []

def save_history():
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(history))
    except Exception as e:
        print("[status] save error:", e)

def ping_service(srv):
    start = time.time()
    st = "down"
    ms = 0.0

    if srv["type"] == "http":
        try:
            req = urllib.request.Request(
                srv["url"],
                headers={"User-Agent": "Gwolf-StatusWatch/1.0"}
            )
            # Timeout 4 detik
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status < 500:
                    st = "up"
        except urllib.error.HTTPError as he:
            # 401 Unauthorized / 302 Redirect = service is UP & responding!
            if he.code < 500:
                st = "up"
        except Exception:
            st = "down"
    elif srv["type"] == "tcp":
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3.0)
            res = s.connect_ex((srv["host"], srv["port"]))
            s.close()
            if res == 0:
                st = "up"
        except Exception:
            st = "down"

    elapsed = (time.time() - start) * 1000.0
    ms = round(elapsed, 1) if st == "up" else 0.0
    return st, ms

def monitor_worker():
    while True:
        now = int(time.time())
        for s in SERVICES:
            sid = s["id"]
            st, ms = ping_service(s)
            item = {"time": now, "status": st, "ms": ms}
            if sid not in history:
                history[sid] = []
            history[sid].append(item)
            # Keep max 40 data points (cukup buat bar chart horizontal)
            if len(history[sid]) > 40:
                history[sid] = history[sid][-40:]
        save_history()
        time.sleep(30) # Poll every 30 seconds

class StatusHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, code=200):
        b = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/" or p == "/index.html":
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                b = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            else:
                self.send_response(404)
                self.end_headers()
            return

        if p == "/api/status":
            result = []
            all_up = True
            for s in SERVICES:
                sid = s["id"]
                h_list = history.get(sid, [])
                last_st = h_list[-1]["status"] if h_list else "unknown"
                last_ms = h_list[-1]["ms"] if h_list else 0.0
                if last_st != "up":
                    all_up = False
                
                # Uptime calculation %
                up_count = sum(1 for x in h_list if x["status"] == "up")
                total_cnt = len(h_list)
                pct = round((up_count / total_cnt) * 100.0, 1) if total_cnt > 0 else 100.0

                result.append({
                    "id": sid,
                    "name": s["name"],
                    "public_url": s["public_url"],
                    "current_status": last_st,
                    "latency_ms": last_ms,
                    "uptime_pct": pct,
                    "bars": [x["status"] for x in h_list]
                })

            self.send_json({
                "all_systems_operational": all_up,
                "timestamp": int(time.time()),
                "services": result
            })
            return

        self.send_response(404)
        self.end_headers()

if __name__ == "__main__":
    load_history()
    t = threading.Thread(target=monitor_worker, daemon=True)
    t.start()
    print(f"Status engine started on port {PORT}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StatusHandler)
    server.serve_forever()
