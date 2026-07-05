# Copyright 2026 Tech4Biz Solutions
# Licensed under the Apache License, Version 2.0

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics"))

import pytest
from suryamon_analytics.kpi import PeriodInputs, compute_kpis, string_anomaly_scores


def test_pr_reference_case():
    # 100 kWp plant, 5.5 kWh/m2 POA day, 440 kWh AC out -> PR = 0.80
    k = compute_kpis(PeriodInputs(
        e_ac_kwh=440.0, e_dc_kwh=460.0, h_poa_kwh_m2=5.5,
        p0_kwp=100.0, period_hours=24.0,
    ))
    assert k.performance_ratio == pytest.approx(0.80, abs=1e-6)
    assert k.final_yield_h == pytest.approx(4.4)
    assert k.specific_yield_kwh_kwp == pytest.approx(4.4)


def test_cuf():
    k = compute_kpis(PeriodInputs(480.0, 500.0, 6.0, 100.0, 24.0))
    assert k.cuf == pytest.approx(0.20)


def test_zero_irradiation_gives_zero_pr():
    k = compute_kpis(PeriodInputs(0.0, 0.0, 0.0, 100.0, 24.0))
    assert k.performance_ratio == 0.0


def test_invalid_capacity_rejected():
    with pytest.raises(ValueError):
        compute_kpis(PeriodInputs(1.0, 1.0, 1.0, 0.0, 24.0))


def test_anomaly_flags_soiled_string():
    currents = {f"inv-01/{i}": 8.0 for i in range(1, 8)}
    currents["inv-01/8"] = 6.0  # 25% down
    scores = string_anomaly_scores(currents)
    assert scores["inv-01/8"] == pytest.approx(0.25)
    assert all(scores[k] == 0.0 for k in scores if k != "inv-01/8")


def test_anomaly_median_resists_dead_string():
    currents = {f"inv-01/{i}": 8.0 for i in range(1, 8)}
    currents["inv-01/8"] = 0.0
    scores = string_anomaly_scores(currents)
    assert scores["inv-01/8"] == pytest.approx(1.0)


def test_anomaly_empty():
    assert string_anomaly_scores({}) == {}
