# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

"""IEC 61724-1 performance KPIs.

Definitions (IEC 61724-1:2021):
  Reference yield   Yr = H_poa / G_stc          [h]
  Array yield       Ya = E_dc / P0              [h]
  Final yield       Yf = E_ac / P0              [h]
  Performance ratio PR = Yf / Yr                [-]
  CUF               = E_ac / (P0 * period_h)    [-]

Where:
  H_poa  plane-of-array irradiation over the period [kWh/m2]
  G_stc  reference irradiance, 1.0 kW/m2
  E_ac   AC energy over the period [kWh]
  E_dc   DC energy over the period [kWh]
  P0     rated DC capacity [kWp]

When no pyranometer exists, Suryamon estimates H_poa from clear-sky
irradiance scaled by observed plant output shape. This is marked
`estimated="true"` on the resulting series so dashboards can show it
honestly. A satellite irradiance source is on the roadmap.
"""

from __future__ import annotations

from dataclasses import dataclass

G_STC_KW_M2 = 1.0


@dataclass
class PeriodInputs:
    e_ac_kwh: float
    e_dc_kwh: float
    h_poa_kwh_m2: float
    p0_kwp: float
    period_hours: float


@dataclass
class PeriodKpis:
    reference_yield_h: float
    array_yield_h: float
    final_yield_h: float
    performance_ratio: float
    cuf: float
    specific_yield_kwh_kwp: float


def compute_kpis(x: PeriodInputs) -> PeriodKpis:
    if x.p0_kwp <= 0:
        raise ValueError("plant capacity must be positive")
    yr = x.h_poa_kwh_m2 / G_STC_KW_M2
    ya = x.e_dc_kwh / x.p0_kwp
    yf = x.e_ac_kwh / x.p0_kwp
    pr = yf / yr if yr > 0 else 0.0
    cuf = x.e_ac_kwh / (x.p0_kwp * x.period_hours) if x.period_hours > 0 else 0.0
    return PeriodKpis(
        reference_yield_h=yr,
        array_yield_h=ya,
        final_yield_h=yf,
        performance_ratio=pr,
        cuf=cuf,
        specific_yield_kwh_kwp=yf,
    )


def string_anomaly_scores(currents_a: dict[str, float]) -> dict[str, float]:
    """Score each string by deviation from the plant-wide median current.

    Score = (median - current) / median, clamped at 0.
    A healthy string scores ~0. A soiled or failing string scores 0.1+.
    Median (not mean) keeps one dead string from masking itself.
    """
    values = sorted(currents_a.values())
    if not values:
        return {}
    n = len(values)
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    if median <= 0:
        return {k: 0.0 for k in currents_a}
    return {k: max(0.0, (median - v) / median) for k, v in currents_a.items()}
