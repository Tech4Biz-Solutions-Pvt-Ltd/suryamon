# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""Integration test: SunSpec reader against the plant simulator over real TCP.

Starts the simulator's Modbus server in-process on an ephemeral port,
then drives the collector's SunSpec reader against it. This exercises the
full wire path: register encoding, model chain walk, scale factors.
"""

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))
sys.path.insert(0, str(ROOT / "simulator"))

from pymodbus.client import AsyncModbusTcpClient  # noqa: E402
from pymodbus.server import StartAsyncTcpServer, ServerAsyncStop  # noqa: E402
from pymodbus.datastore import (  # noqa: E402
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
)

from suryamon_collector.sunspec import read_common, read_inverter, read_mppt  # noqa: E402
from suryamon_simulator.simulator import BASE, build_map, STRINGS, SOILED  # noqa: E402

PORT = 15511


async def _serve(context):
    await StartAsyncTcpServer(context=context, address=("127.0.0.1", PORT))


@pytest.mark.parametrize("unit_id", [1, 2])
def test_sunspec_roundtrip(unit_id):
    async def scenario():
        slaves = {
            uid: ModbusSlaveContext(
                hr=ModbusSequentialDataBlock(0, [0] * 45100), zero_mode=True
            )
            for uid in (1, 2)
        }
        context = ModbusServerContext(slaves=slaves, single=False)
        # Write a known mid-day state: 46 kW AC, 1234 kWh lifetime, 55C
        for uid in (1, 2):
            context[uid].setValues(3, BASE, build_map(uid, 46_000.0, 1_234_000.0, 55.0))

        server = asyncio.create_task(_serve(context))
        await asyncio.sleep(0.5)
        try:
            client = AsyncModbusTcpClient("127.0.0.1", port=PORT)
            await client.connect()
            assert client.connected

            common = await read_common(client, unit_id)
            assert common.manufacturer == "Tech4Biz"
            assert common.serial == f"SN-{unit_id:04d}"

            inv = await read_inverter(client, unit_id)
            # W_SF=1 quantises to tens of watts
            assert inv.ac_power_w == pytest.approx(46_000.0, abs=10)
            assert inv.dc_power_w == pytest.approx(46_000.0 * 1.04, abs=10)
            assert inv.energy_wh == pytest.approx(1_234_000.0, abs=1)
            assert inv.cabinet_temp_c == pytest.approx(55.0, abs=0.1)
            assert inv.status == 4  # MPPT

            mppt = await read_mppt(client, unit_id)
            assert len(mppt.strings) == STRINGS
            healthy = [s.current_a for s in mppt.strings if (unit_id, s.index) not in SOILED]
            for s in mppt.strings:
                factor = SOILED.get((unit_id, s.index), 1.0)
                expected = (sum(healthy) / len(healthy)) * factor
                assert s.current_a == pytest.approx(expected, rel=0.05)
                assert 580 < s.voltage_v < 660

            client.close()
        finally:
            await ServerAsyncStop()
            server.cancel()

    asyncio.run(scenario())
