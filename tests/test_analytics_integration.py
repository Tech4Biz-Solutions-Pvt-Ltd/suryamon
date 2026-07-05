# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Integration test: analytics service against a VictoriaMetrics-compatible API.

Spins up a local HTTP server that implements the two VM endpoints the
analytics service uses (/api/v1/query, /api/v1/import/prometheus), runs
one full analytics pass, and asserts the derived series written back.
"""

import json
import pathlib
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics"))

from suryamon_analytics.service import run_once  # noqa: E402

# Simulated plant day: 100 kWp, 5.5 kWh/m2 POA, 440 kWh AC -> PR must be 0.80
QUERY_RESPONSES = {
    "suryamon_energy_lifetime_wh": [{"metric": {}, "value": [0, "440.0"]}],
    "suryamon_dc_power_watts": [{"metric": {}, "value": [0, "19166.6667"]}],  # *24/1000 = 460 kWh DC
    "suryamon_poa_irradiation_kwh_m2": [{"metric": {}, "value": [0, "5.5"]}],
    "suryamon_string_current_amps": [
        {"metric": {"inverter": "inv-01", "string": str(i)}, "value": [0, "8.0"]}
        for i in range(1, 8)
    ] + [{"metric": {"inverter": "inv-01", "string": "8"}, "value": [0, "6.0"]}],
}

written_lines: list[str] = []


class FakeVM(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query).get("query", [""])[0]
        result = []
        for key, resp in QUERY_RESPONSES.items():
            if key in q:
                result = resp
                break
        body = json.dumps({"status": "success", "data": {"result": result}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        written_lines.extend(self.rfile.read(length).decode().strip().splitlines())
        self.send_response(204)
        self.end_headers()


def test_analytics_end_to_end():
    server = HTTPServer(("127.0.0.1", 0), FakeVM)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        written_lines.clear()
        run_once(f"http://127.0.0.1:{port}", plant="demo-rooftop", p0_kwp=100.0)
    finally:
        server.shutdown()

    joined = "\n".join(written_lines)

    # PR = (440/100) / (5.5/1.0) = 0.80
    m = re.search(r'suryamon_performance_ratio\{[^}]*\} ([\d.]+)', joined)
    assert m, f"PR series missing in:\n{joined}"
    assert abs(float(m.group(1)) - 0.80) < 1e-3

    # CUF = 440 / (100*24) = 0.1833
    m = re.search(r'suryamon_cuf\{[^}]*\} ([\d.]+)', joined)
    assert m and abs(float(m.group(1)) - 0.1833) < 1e-3

    # Specific yield = 4.4 kWh/kWp
    m = re.search(r'suryamon_specific_yield_kwh_kwp\{[^}]*\} ([\d.]+)', joined)
    assert m and abs(float(m.group(1)) - 4.4) < 1e-3

    # Soiled string 8 scores 0.25, healthy strings 0
    m = re.search(r'suryamon_string_anomaly_score\{[^}]*string="8"\} ([\d.]+)', joined)
    assert m and abs(float(m.group(1)) - 0.25) < 1e-3
    m = re.search(r'suryamon_string_anomaly_score\{[^}]*string="1"\} ([\d.]+)', joined)
    assert m and float(m.group(1)) == 0.0
