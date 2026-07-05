# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Suryamon collector.

Polls SunSpec-compliant inverters over Modbus TCP and exposes readings
as Prometheus metrics on /metrics.

SunSpec models used:
  - Model 1   (Common): manufacturer, model, serial
  - Model 103 (Three-phase inverter): AC power, energy, temps, status
  - Model 160 (MPPT extension): per-string DC current/voltage/power
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import yaml
from prometheus_client import Counter, Gauge, start_http_server
from pymodbus.client import AsyncModbusTcpClient

from .sunspec import read_common, read_inverter, read_mppt

log = logging.getLogger("suryamon.collector")

# --- Prometheus metrics -----------------------------------------------------

LABELS = ["plant", "inverter"]
STRING_LABELS = ["plant", "inverter", "string"]

AC_POWER_W = Gauge("suryamon_ac_power_watts", "AC active power", LABELS)
DC_POWER_W = Gauge("suryamon_dc_power_watts", "DC power", LABELS)
ENERGY_WH = Gauge("suryamon_energy_lifetime_wh", "Lifetime AC energy", LABELS)
CABINET_TEMP_C = Gauge("suryamon_cabinet_temp_celsius", "Cabinet temperature", LABELS)
STATUS = Gauge("suryamon_inverter_status", "SunSpec operating state enum", LABELS)
STRING_CURRENT_A = Gauge("suryamon_string_current_amps", "DC string current", STRING_LABELS)
STRING_VOLTAGE_V = Gauge("suryamon_string_voltage_volts", "DC string voltage", STRING_LABELS)
POLL_ERRORS = Counter("suryamon_poll_errors_total", "Modbus poll failures", LABELS)
UP = Gauge("suryamon_inverter_up", "1 if last poll succeeded", LABELS)


async def poll_inverter(plant: str, inv: dict, interval: float) -> None:
    """Poll one inverter forever. Reconnects on failure with backoff."""
    labels = {"plant": plant, "inverter": inv["id"]}
    backoff = interval
    while True:
        client = AsyncModbusTcpClient(inv["host"], port=inv.get("port", 502))
        try:
            await client.connect()
            if not client.connected:
                raise ConnectionError(f"cannot reach {inv['host']}")
            common = await read_common(client, inv.get("unit_id", 1))
            log.info("connected: %s %s sn=%s", common.manufacturer, common.model, common.serial)
            backoff = interval
            while True:
                data = await read_inverter(client, inv.get("unit_id", 1))
                AC_POWER_W.labels(**labels).set(data.ac_power_w)
                DC_POWER_W.labels(**labels).set(data.dc_power_w)
                ENERGY_WH.labels(**labels).set(data.energy_wh)
                CABINET_TEMP_C.labels(**labels).set(data.cabinet_temp_c)
                STATUS.labels(**labels).set(data.status)
                UP.labels(**labels).set(1)
                mppt = await read_mppt(client, inv.get("unit_id", 1))
                for s in mppt.strings:
                    slab = {**labels, "string": str(s.index)}
                    STRING_CURRENT_A.labels(**slab).set(s.current_a)
                    STRING_VOLTAGE_V.labels(**slab).set(s.voltage_v)
                await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001 - top-level poll loop must survive
            POLL_ERRORS.labels(**labels).inc()
            UP.labels(**labels).set(0)
            log.warning("poll failed for %s: %s; retrying in %.0fs", inv["id"], exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)
        finally:
            client.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config_path = os.environ.get("SURYAMON_CONFIG", "/etc/suryamon/plant.yaml")
    interval = float(os.environ.get("SURYAMON_POLL_INTERVAL", "10"))
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    plant = cfg["plant"]["name"]
    start_http_server(9101)
    log.info("metrics on :9101/metrics, polling every %.0fs", interval)

    tasks = [poll_inverter(plant, inv, interval) for inv in cfg["inverters"]]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
