# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Suryamon plant simulator.

Emulates a 100 kWp plant behind two SunSpec inverters on one Modbus TCP
endpoint (unit IDs 1 and 2). Produces a realistic bell-shaped irradiance
curve, cloud noise, and one deliberately soiled string (inv 1, string 3,
25% down) so alert rules fire during demos.

Register map written per SunSpec: Common (1), Inverter (103), MPPT (160).
"""

from __future__ import annotations

import asyncio
import math
import random
import struct
import time

from pymodbus.datastore import (
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
)
from pymodbus.server import StartAsyncTcpServer

BASE = 40000
RATED_W_PER_INV = 50_000
STRINGS = 8
SOILED = {(1, 3): 0.75}  # (unit_id, string_index) -> output factor
DAY_SECONDS = 600  # one simulated day every 10 minutes


def _str16(s: str, words: int) -> list[int]:
    raw = s.encode("ascii")[: words * 2].ljust(words * 2, b"\x00")
    return list(struct.unpack(f">{words}H", raw))


def _u16(v: float) -> int:
    return max(0, min(0xFFFF, int(v)))


def build_map(unit_id: int, ac_w: float, energy_wh: float, temp_c: float) -> list[int]:
    """Return the full register block starting at BASE."""
    regs: list[int] = [0x5375, 0x6E53]  # 'SunS'

    # Model 1: Common (length 66)
    regs += [1, 66]
    common = _str16("Tech4Biz", 16) + _str16("SIM-50K", 16) + [0] * 16 + _str16(f"SN-{unit_id:04d}", 16) + [0, 0]
    regs += common[:66]

    # Model 103: three-phase inverter (length 50)
    regs += [103, 50]
    m103 = [0] * 50
    m103[12] = _u16(ac_w / 10)     # W stored in tens of watts (int16 max 32767)
    m103[13] = 1                   # W_SF = 1
    e = int(energy_wh)
    m103[22] = (e >> 16) & 0xFFFF  # WH high
    m103[23] = e & 0xFFFF          # WH low
    m103[24] = 0                   # WH_SF
    m103[29] = _u16(ac_w * 1.04 / 10)  # DCW in tens of watts
    m103[30] = 1                   # DCW_SF = 1
    m103[31] = _u16(temp_c * 10)   # TmpCab
    m103[34] = (0x10000 - 1) & 0xFFFF  # Tmp_SF = -1
    m103[36] = 4                   # St = MPPT
    regs += m103

    # Model 160: MPPT (header 10 + 20 per module)
    regs += [160, 10 + 20 * STRINGS]
    dca_sf = (0x10000 - 2) & 0xFFFF  # -2: centiamps
    dcv_sf = 0
    head = [dca_sf, dcv_sf, 0, 0, 0, 0, 0, 0, STRINGS, 0]
    regs += head
    per_string_w = (ac_w * 1.04) / STRINGS
    for i in range(1, STRINGS + 1):
        factor = SOILED.get((unit_id, i), 1.0)
        voltage = 620.0 + random.uniform(-5, 5)
        current = (per_string_w * factor) / voltage
        module = [0] * 20
        module[9] = _u16(current * 100)  # DCA in centiamps
        module[10] = _u16(voltage)       # DCV
        module[11] = _u16(per_string_w * factor)
        regs += module

    regs += [0xFFFF, 0]  # end marker
    return regs


def irradiance_factor(t: float) -> float:
    """Bell curve over the simulated day plus cloud noise."""
    phase = (t % DAY_SECONDS) / DAY_SECONDS  # 0..1
    if phase < 0.2 or phase > 0.8:
        return 0.0
    bell = math.sin(math.pi * (phase - 0.2) / 0.6)
    cloud = 1.0 - max(0.0, random.gauss(0, 0.08))
    return max(0.0, bell * cloud)


async def update_loop(context: ModbusServerContext, energy: dict[int, float]) -> None:
    # Start at simulated mid-day so demos show production immediately.
    t0 = time.monotonic() - DAY_SECONDS * 0.5
    while True:
        t = time.monotonic() - t0
        f = irradiance_factor(t)
        for unit_id in (1, 2):
            ac_w = RATED_W_PER_INV * f * (1.0 if unit_id == 1 else 0.98)
            energy[unit_id] += ac_w * (2.0 / 3600.0)
            temp = 35 + 25 * f
            block = build_map(unit_id, ac_w, energy[unit_id], temp)
            slave = context[unit_id]
            slave.setValues(3, BASE, block)
        await asyncio.sleep(2)


async def main() -> None:
    slaves = {
        uid: ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 45100), zero_mode=True)
        for uid in (1, 2)
    }
    context = ModbusServerContext(slaves=slaves, single=False)
    energy = {1: 0.0, 2: 0.0}
    asyncio.create_task(update_loop(context, energy))
    print("Suryamon simulator: 2 inverters on :1502 (unit 1 and 2), string 3 on unit 1 is soiled")
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 1502))


if __name__ == "__main__":
    asyncio.run(main())
