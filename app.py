#!/usr/bin/env python3
"""
Gwolf Status Page — Ultra-Lightweight Monitoring Engine with System Telemetry
Running on Termux Android (Port 3002)
Target: https://status.gwolfdev.my.id
"""

import time
import json
import socket
import urllib.request
import urllib.error
import threading
import subprocess
import os
import shutil
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
        "id": "status_web",
        "name": "Status Engine",
        "url": "http://127.0.0.1:3002",
        "public_url": "https://status.gwolfdev.my.id",
        "type": "http"
    },
    {
        "id": "cf_tunnel",
        "name": "Cloudflare Tunnel",
        "public_url": "gwolfdev.my.id • gwolfdev.me",
        "type": "cf_tunnel"
    },
    {
        "id": "ssh_gateway",
        "name": "SSH Remote Terminal",
        "host": "127.0.0.1",
        "port": 8022,
        "public_url": "Termux Port 8022",
        "type": "tcp"
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

def get_system_telemetry():
    # RAM & Swap
    mem_used, mem_total, mem_avail = 0, 0, 0
    swap_used, swap_total = 0, 0
    try:
        lines = subprocess.check_output(["free", "-m"], timeout=2).decode("utf-8").splitlines()
        if len(lines) >= 2:
            p = lines[1].split()
            mem_total = int(p[1])
            mem_used = int(p[2])
            mem_avail = int(p[6]) if len(p) > 6 else int(p[3])
        if len(lines) >= 3:
            s = lines[2].split()
            swap_total = int(s[1])
            swap_used = int(s[2])
    except Exception:
        pass

    # Disk
    disk_total, disk_used, disk_free = 0, 0, 0
    try:
        du = shutil.disk_usage(os.path.expanduser("~"))
        disk_total = round(du.total / (1024**3), 1)
        disk_used = round((du.total - du.free) / (1024**3), 1)
        disk_free = round(du.free / (1024**3), 1)
    except Exception:
        pass

    # Thermal
    temp_c = 0
    try:
        for f in os.listdir("/sys/class/thermal/"):
            if f.startswith("thermal_zone"):
                tpath = f"/sys/class/thermal/{f}/type"
                if os.path.exists(tpath):
                    with open(tpath, "r") as tf:
                        typ = tf.read().strip()
                    if any(x in typ for x in ["vbat", "battery", "pm6125"]):
                        with open(f"/sys/class/thermal/{f}/temp", "r") as vf:
                            v = int(vf.read().strip())
                            if v > 1000:
                                temp_c = v // 1000
                                break
    except Exception:
        pass

    cf_alive = subprocess.run(["pgrep", "-f", "cloudflared tunnel"], stdout=subprocess.DEVNULL).returncode == 0

    return {
        "ram": {
            "used_mb": mem_used,
            "total_mb": mem_total,
            "avail_mb": mem_avail,
            "pct": round((mem_used / mem_total) * 100, 1) if mem_total else 0
        },
        "swap": {
            "used_mb": swap_used,
            "total_mb": swap_total,
            "pct": round((swap_used / swap_total) * 100, 1) if swap_total else 0
        },
        "disk": {
            "used_gb": disk_used,
            "total_gb": disk_total,
            "free_gb": disk_free,
            "pct": round((disk_used / disk_total) * 100, 1) if disk_total else 0
        },
        "temp_c": temp_c,
        "cloudflared_running": cf_alive
    }

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
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status < 500:
                    st = "up"
        except urllib.error.HTTPError as he:
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
    elif srv["type"] == "cf_tunnel":
        cf_alive = subprocess.run(["pgrep", "-f", "cloudflared tunnel"], stdout=subprocess.DEVNULL).returncode == 0
        if cf_alive:
            try:
                req = urllib.request.Request("https://1.1.1.1/cdn-cgi/trace", headers={"User-Agent": "Gwolf-StatusWatch/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        st = "up"
            except Exception:
                st = "up"
        else:
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
            if len(history[sid]) > 40:
                history[sid] = history[sid][-40:]
        save_history()
        time.sleep(30)

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
                "system": get_system_telemetry(),
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
