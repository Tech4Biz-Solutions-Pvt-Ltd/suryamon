# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Analytics loop.

Every COMPUTE_INTERVAL seconds:
  1. Query VictoriaMetrics for the trailing day's energy and irradiation.
  2. Compute IEC 61724-1 KPIs and string anomaly scores.
  3. Write derived series back to VictoriaMetrics via /api/v1/import/prometheus.

Derived series:
  suryamon_performance_ratio{plant,window="1d"}
  suryamon_cuf{plant,window="1d"}
  suryamon_specific_yield_kwh_kwp{plant,window="1d"}
  suryamon_string_anomaly_score{plant,inverter,string}
"""

from __future__ import annotations

import logging
import os
import time

import requests
import yaml

from .kpi import PeriodInputs, compute_kpis, string_anomaly_scores

log = logging.getLogger("suryamon.analytics")


def query(vm_url: str, promql: str) -> list[dict]:
    r = requests.get(f"{vm_url}/api/v1/query", params={"query": promql}, timeout=30)
    r.raise_for_status()
    return r.json()["data"]["result"]


def scalar(vm_url: str, promql: str, default: float = 0.0) -> float:
    result = query(vm_url, promql)
    return float(result[0]["value"][1]) if result else default


def write(vm_url: str, lines: list[str]) -> None:
    body = "\n".join(lines)
    r = requests.post(f"{vm_url}/api/v1/import/prometheus", data=body, timeout=30)
    r.raise_for_status()


def run_once(vm_url: str, plant: str, p0_kwp: float) -> None:
    e_ac = scalar(vm_url, f'sum(increase(suryamon_energy_lifetime_wh{{plant="{plant}"}}[1d])) / 1000')
    # DC energy integrated from DC power samples (avg power * hours).
    e_dc = scalar(vm_url, f'sum(avg_over_time(suryamon_dc_power_watts{{plant="{plant}"}}[1d])) * 24 / 1000')
    h_poa = scalar(vm_url, f'suryamon_poa_irradiation_kwh_m2{{plant="{plant}",window="1d"}}', default=0.0)

    lines: list[str] = []
    if h_poa > 0:
        k = compute_kpis(PeriodInputs(e_ac, e_dc, h_poa, p0_kwp, period_hours=24.0))
        lines += [
            f'suryamon_performance_ratio{{plant="{plant}",window="1d"}} {k.performance_ratio:.4f}',
            f'suryamon_cuf{{plant="{plant}",window="1d"}} {k.cuf:.4f}',
            f'suryamon_specific_yield_kwh_kwp{{plant="{plant}",window="1d"}} {k.specific_yield_kwh_kwp:.3f}',
        ]
    else:
        log.info("no irradiation series yet; skipping PR (specific yield still written)")
        lines.append(
            f'suryamon_specific_yield_kwh_kwp{{plant="{plant}",window="1d"}} {e_ac / p0_kwp:.3f}'
        )

    currents = {
        f'{m["metric"]["inverter"]}/{m["metric"]["string"]}': float(m["value"][1])
        for m in query(vm_url, f'suryamon_string_current_amps{{plant="{plant}"}}')
    }
    for key, score in string_anomaly_scores(currents).items():
        inverter, string = key.split("/", 1)
        lines.append(
            f'suryamon_string_anomaly_score{{plant="{plant}",inverter="{inverter}",string="{string}"}} {score:.4f}'
        )

    if lines:
        write(vm_url, lines)
        log.info("wrote %d derived series", len(lines))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    vm_url = os.environ.get("VM_URL", "http://victoriametrics:8428")
    interval = float(os.environ.get("COMPUTE_INTERVAL", "300"))
    with open(os.environ.get("SURYAMON_CONFIG", "/etc/suryamon/plant.yaml")) as f:
        cfg = yaml.safe_load(f)
    plant = cfg["plant"]["name"]
    p0 = float(cfg["plant"]["capacity_kwp"])

    while True:
        try:
            run_once(vm_url, plant, p0)
        except Exception as exc:  # noqa: BLE001 - service loop must survive
            log.warning("analytics pass failed: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
