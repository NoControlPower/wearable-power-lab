"""Regression tests for the power budget model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import power_budget as pb  # noqa: E402


def test_charge_is_current_times_time():
    phase = pb.Phase(name="p", current_ua=1000.0, seconds_per_day=3600.0)
    assert phase.mah_per_day() == pytest.approx(1.0)


def test_average_current_from_daily_charge():
    phase = pb.Phase(name="p", current_ua=1000.0, seconds_per_day=3600.0)
    budget = pb.Budget(battery_mah=10.0, phases=(phase,))
    assert budget.average_current_ua == pytest.approx(41.667, rel=1e-3)


def test_days_of_battery_life():
    phase = pb.Phase(name="p", current_ua=100.0, seconds_per_day=86400.0)
    budget = pb.Budget(battery_mah=10.0, phases=(phase,))
    # 100 uA for a full day = 2.4 mAh -> 10 mAh / 2.4 = 4.1667 days
    assert budget.total_mah_per_day == pytest.approx(2.4)
    assert budget.days == pytest.approx(4.1667, rel=1e-3)


def test_sensitivity_ranks_largest_phase_first():
    big = pb.Phase(name="big", current_ua=1000.0, seconds_per_day=3600.0)
    small = pb.Phase(name="small", current_ua=10.0, seconds_per_day=3600.0)
    budget = pb.Budget(battery_mah=10.0, phases=(big, small))
    ranked = pb.sensitivity(budget)
    assert ranked[0][0].name == "big"
    assert ranked[0][1] > ranked[1][1]


def test_seconds_beyond_a_day_is_rejected():
    raw = {
        "battery_mah": 21,
        "phases": [{"name": "x", "current_ua": 100, "seconds_per_day": 90000}],
    }
    with pytest.raises(pb.SpecError):
        pb.build_budgets(raw)


def test_negative_current_is_rejected():
    raw = {
        "battery_mah": 21,
        "phases": [{"name": "x", "current_ua": -1, "seconds_per_day": 10}],
    }
    with pytest.raises(pb.SpecError):
        pb.build_budgets(raw)


def test_example_table_loads():
    spec = pb.load_spec(ROOT / "examples" / "duty_table.example.json")
    budgets = pb.build_budgets(spec)
    assert len(budgets) == 3
    assert budgets[-1].battery_mah == 21
    assert budgets[-1].days > 0


def test_cli_json_output(capsys):
    rc = pb.main(
        [
            str(ROOT / "examples" / "duty_table.example.json"),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["battery_mah"] == 13
    assert payload[-1]["battery_mah"] == 21
