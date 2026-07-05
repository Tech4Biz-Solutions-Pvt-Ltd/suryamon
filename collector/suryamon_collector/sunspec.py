# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Minimal SunSpec register reader.

Implements just enough of the SunSpec information model to monitor a plant:
Model 1 (Common), Model 103 (three-phase inverter), Model 160 (MPPT).

SunSpec devices anchor the register map at one of three base addresses and
mark it with the 'SunS' magic word (0x53756E53). Models follow as a linked
list of (model_id, length) blocks.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from pymodbus.client import AsyncModbusTcpClient

SUNS_MAGIC = 0x53756E53
BASE_ADDRESSES = (40000, 0, 50000)
END_MODEL = 0xFFFF


@dataclass
class CommonInfo:
    manufacturer: str
    model: str
    serial: str


@dataclass
class InverterReading:
    ac_power_w: float
    dc_power_w: float
    energy_wh: float
    cabinet_temp_c: float
    status: int


@dataclass
class StringReading:
    index: int
    current_a: float
    voltage_v: float


@dataclass
class MpptReading:
    strings: list[StringReading] = field(default_factory=list)


def _to_str(registers: list[int]) -> str:
    raw = b"".join(struct.pack(">H", r) for r in registers)
    return raw.split(b"\x00")[0].decode("ascii", errors="replace").strip()


def _i16(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


def _scaled(value: int, sf: int, signed: bool = True) -> float:
    if signed:
        value = _i16(value)
    sf = _i16(sf)
    return float(value) * (10.0 ** sf)


async def _read(client: AsyncModbusTcpClient, addr: int, count: int, unit: int) -> list[int]:
    rr = await client.read_holding_registers(addr, count, slave=unit)
    if rr.isError():
        raise IOError(f"modbus read error at {addr}: {rr}")
    return rr.registers


async def _find_base(client: AsyncModbusTcpClient, unit: int) -> int:
    for base in BASE_ADDRESSES:
        try:
            regs = await _read(client, base, 2, unit)
            if (regs[0] << 16 | regs[1]) == SUNS_MAGIC:
                return base + 2
        except IOError:
            continue
    raise IOError("no SunSpec magic word found; device is not SunSpec compliant")


async def _walk_models(client: AsyncModbusTcpClient, unit: int) -> dict[int, tuple[int, int]]:
    """Return {model_id: (data_start_addr, length)} for every model on the device."""
    addr = await _find_base(client, unit)
    models: dict[int, tuple[int, int]] = {}
    while True:
        header = await _read(client, addr, 2, unit)
        model_id, length = header
        if model_id == END_MODEL:
            break
        models[model_id] = (addr + 2, length)
        addr += 2 + length
    return models


async def read_common(client: AsyncModbusTcpClient, unit: int) -> CommonInfo:
    models = await _walk_models(client, unit)
    start, _ = models[1]
    regs = await _read(client, start, 64, unit)
    return CommonInfo(
        manufacturer=_to_str(regs[0:16]),
        model=_to_str(regs[16:32]),
        serial=_to_str(regs[48:64]),
    )


async def read_inverter(client: AsyncModbusTcpClient, unit: int) -> InverterReading:
    models = await _walk_models(client, unit)
    model_id = next((m for m in (103, 102, 101) if m in models), None)
    if model_id is None:
        raise IOError("no inverter model (101/102/103) on device")
    start, length = models[model_id]
    regs = await _read(client, start, length, unit)
    # Offsets per SunSpec inverter model (relative to data start):
    # 12=W 13=W_SF, 22/23=WH(acc32) 24=WH_SF, 25=DCA 26=DCA_SF,
    # 27=DCV 28=DCV_SF, 29=DCW 30=DCW_SF, 31=TmpCab 34=Tmp_SF, 36=St
    ac_power = _scaled(regs[12], regs[13])
    energy = float(regs[22] << 16 | regs[23]) * (10.0 ** _i16(regs[24]))
    dc_power = _scaled(regs[29], regs[30])
    cabinet = _scaled(regs[31], regs[34])
    status = regs[36]
    return InverterReading(ac_power, dc_power, energy, cabinet, status)


async def read_mppt(client: AsyncModbusTcpClient, unit: int) -> MpptReading:
    models = await _walk_models(client, unit)
    if 160 not in models:
        return MpptReading()
    start, _ = models[160]
    head = await _read(client, start, 10, unit)
    dca_sf, dcv_sf, n = _i16(head[0]), _i16(head[1]), head[8]
    out = MpptReading()
    module_start = start + 10
    module_len = 20
    for i in range(n):
        regs = await _read(client, module_start + i * module_len, module_len, unit)
        out.strings.append(
            StringReading(
                index=i + 1,
                current_a=float(regs[9]) * (10.0 ** dca_sf),
                voltage_v=float(regs[10]) * (10.0 ** dcv_sf),
            )
        )
    return out
