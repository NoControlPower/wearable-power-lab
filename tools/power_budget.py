#!/usr/bin/env python3
"""Average-current power budget for sub-mA wearables.

Turns a duty-cycle table into daily charge (mAh/day), predicted battery life,
and a sensitivity ranking ("halve this phase, gain how many hours?").

Model
-----
    mAh/day  = SUM(current_mA * seconds_per_day) / 3600
    days     = battery_mAh / mAh_per_day
    uA_avg   = mAh_per_day * 1000 / 24

Phases MUST be mutually exclusive (see docs/methodology.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SECONDS_PER_DAY = 86_400.0
SECONDS_PER_HOUR = 3_600.0


class SpecError(ValueError):
    """Raised when a duty-cycle table is malformed."""


@dataclass(frozen=True)
class Phase:
    name: str
    current_ua: float
    seconds_per_day: float

    def mah_per_day(self) -> float:
        """Charge drawn by this phase per day, in mAh."""
        return self.current_ua * self.seconds_per_day / SECONDS_PER_HOUR / 1000.0


@dataclass(frozen=True)
class Budget:
    battery_mah: float
    phases: tuple[Phase, ...]

    @property
    def total_mah_per_day(self) -> float:
        return sum(p.mah_per_day() for p in self.phases)

    @property
    def days(self) -> float:
        total = self.total_mah_per_day
        if total <= 0.0:
            return float("inf")
        return self.battery_mah / total

    @property
    def average_current_ua(self) -> float:
        return self.total_mah_per_day * 1000.0 / 24.0


def _as_positive_number(value: object, field: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SpecError(f"{field} must be a number, got {value!r}") from exc
    if number < 0:
        raise SpecError(f"{field} must be >= 0, got {number}")
    return number


def parse_phases(raw: object) -> tuple[Phase, ...]:
    if not isinstance(raw, list) or not raw:
        raise SpecError("'phases' must be a non-empty list")
    phases: list[Phase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SpecError(f"phases[{index}] must be an object")
        missing = {"name", "current_ua", "seconds_per_day"} - item.keys()
        if missing:
            raise SpecError(f"phases[{index}] missing field(s): {sorted(missing)}")
        name = str(item["name"]).strip()
        if not name:
            raise SpecError(f"phases[{index}].name must not be empty")
        current = _as_positive_number(item["current_ua"], f"phases[{index}].current_ua")
        seconds = _as_positive_number(
            item["seconds_per_day"], f"phases[{index}].seconds_per_day"
        )
        if seconds > SECONDS_PER_DAY:
            raise SpecError(
                f"phases[{index}].seconds_per_day > 86400; "
                "phases must be mutually exclusive"
            )
        phases.append(Phase(name=name, current_ua=current, seconds_per_day=seconds))
    return tuple(phases)


def load_spec(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SpecError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(spec, dict):
        raise SpecError("top level must be an object")
    return spec


def build_budgets(spec: dict) -> list[Budget]:
    phases = parse_phases(spec.get("phases"))
    batteries = spec.get("battery_mah")
    if isinstance(batteries, (int, float)):
        batteries = [batteries]
    if not isinstance(batteries, list) or not batteries:
        raise SpecError("'battery_mah' must be a number or a non-empty list")
    capacities = tuple(
        _as_positive_number(value, f"battery_mah[{i}]")
        for i, value in enumerate(batteries)
    )
    return [Budget(battery_mah=capacity, phases=phases) for capacity in capacities]


def sensitivity(budget: Budget, factor: float = 0.5) -> list[tuple[Phase, float]]:
    """Return (phase, extra days) if that phase's charge is multiplied by factor.

    Sorted by the largest gain first.
    """
    results: list[tuple[Phase, float]] = []
    base_days = budget.days
    for phase in budget.phases:
        saved = phase.mah_per_day() * (1.0 - factor)
        new_total = budget.total_mah_per_day - saved
        if new_total <= 0.0:
            gain = float("inf")
        else:
            gain = budget.battery_mah / new_total - base_days
        results.append((phase, gain))
    results.sort(key=lambda item: item[1], reverse=True)
    return results


def render(spec: dict, budgets: list[Budget], show_sensitivity: bool) -> str:
    name = spec.get("name", "unnamed")
    lines = [f"device: {name}", ""]
    reference = budgets[-1]
    lines.append(f"reference battery: {reference.battery_mah:g} mAh")
    lines.append("")
    lines.append(f"{'battery (mAh)':>14}  {'avg current (uA)':>17}  {'days':>8}")
    for budget in budgets:
        lines.append(
            f"{budget.battery_mah:>14.1f}  "
            f"{budget.average_current_ua:>17.1f}  "
            f"{budget.days:>8.2f}"
        )
    lines.append("")
    lines.append(f"{'phase':<32}{'uA':>10}{'s/day':>10}{'mAh/day':>11}{'share':>8}")
    total = reference.total_mah_per_day
    for phase in sorted(reference.phases, key=Phase.mah_per_day, reverse=True):
        share = phase.mah_per_day() / total * 100.0 if total > 0 else 0.0
        lines.append(
            f"{phase.name:<32}{phase.current_ua:>10.0f}"
            f"{phase.seconds_per_day:>10.0f}{phase.mah_per_day():>11.3f}"
            f"{share:>7.1f}%"
        )
    lines.append(
        f"{'TOTAL':<32}{'':>10}{'':>10}{reference.total_mah_per_day:>11.3f}"
        f"{100.0:>7.1f}%"
    )

    if show_sensitivity:
        lines.append("")
        lines.append(
            f"sensitivity (halve one phase, battery = {reference.battery_mah:g} mAh):"
        )
        for phase, gain in sensitivity(reference):
            if gain == float("inf"):
                lines.append(f"  {phase.name:<32} unlimited")
            else:
                lines.append(
                    f"  {phase.name:<32} +{gain * 24.0:6.1f} h "
                    f"({gain:+.2f} d)"
                )
    return "\n".join(lines)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse plumbing
        self.print_usage(sys.stderr)
        raise SystemExit(f"error: {message}")


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("table", type=Path, help="duty-cycle table (JSON)")
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="show hours gained if one phase is halved",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.table)
        budgets = build_budgets(spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = [
            {
                "battery_mah": budget.battery_mah,
                "average_current_ua": round(budget.average_current_ua, 2),
                "days": None if budget.days == float("inf") else round(budget.days, 3),
                "phases": [
                    {
                        "name": phase.name,
                        "mah_per_day": round(phase.mah_per_day(), 4),
                    }
                    for phase in budget.phases
                ],
            }
            for budget in budgets
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(render(spec, budgets, args.sensitivity))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
