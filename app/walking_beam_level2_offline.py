from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass


@dataclass
class ZoneResult:
    zone_name: str
    residence_time_s: float
    furnace_setpoint_c: float
    surface_temp_c: float
    core_temp_c: float
    average_temp_c: float
    temp_rise_rate_c_per_min: float


DEFAULT_CASE = {
    "billet": {
        "width_m": 0.16,
        "thickness_m": 0.12,
        "length_m": 6.0,
        "density": 7850.0,
        "specific_heat": 680.0,
        "conductivity": 32.0,
        "emissivity": 0.82,
    },
    "process": {
        "entry_temp_c": 35.0,
        "target_exit_temp_c": 1180.0,
        "max_core_surface_delta_c": 45.0,
        "max_rise_rate_c_per_min": 28.0,
        "step_length_m": 0.75,
        "step_cycle_s": 48.0,
    },
    "zones": [
        {"name": "预热段", "length_m": 8.0, "furnace_temp_c": 980.0, "heat_transfer_coeff": 120.0},
        {"name": "加热段", "length_m": 11.0, "furnace_temp_c": 1210.0, "heat_transfer_coeff": 168.0},
        {"name": "均热段", "length_m": 7.0, "furnace_temp_c": 1195.0, "heat_transfer_coeff": 142.0},
    ],
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round2(value: float) -> float:
    return round(value, 2)


def merge_case(context: dict) -> dict:
    node_meta = context.get("node_metadata") or {}
    inputs = context.get("inputs") or {}
    project_params = context.get("project_params") or {}
    payload = context.get("model_payload") or {}

    billet = dict(DEFAULT_CASE["billet"])
    process = dict(DEFAULT_CASE["process"])
    zones = [dict(zone) for zone in DEFAULT_CASE["zones"]]

    billet.update(payload.get("billet") or {})
    process.update(payload.get("process") or {})

    for field in billet:
        if field in inputs:
            billet[field] = inputs[field]
        if field in project_params:
            billet[field] = project_params[field]
    for field in process:
        if field in inputs:
            process[field] = inputs[field]
        if field in project_params:
            process[field] = project_params[field]

    zone_overrides = payload.get("zones")
    if isinstance(zone_overrides, list) and zone_overrides:
        zones = [dict(zone) for zone in zone_overrides]

    furnace_type = node_meta.get("furnace_type", "步进炉")
    model_level = node_meta.get("model_level", "二级")
    model_mode = node_meta.get("model_mode", "offline")
    return {
        "billet": billet,
        "process": process,
        "zones": zones,
        "furnace_type": furnace_type,
        "model_level": model_level,
        "model_mode": model_mode,
    }


def simulate(case_data: dict, optimize: bool) -> dict:
    billet = case_data["billet"]
    process = case_data["process"]
    zones = case_data["zones"]

    current_surface = float(process["entry_temp_c"])
    current_core = current_surface
    target_exit = float(process["target_exit_temp_c"])
    total_zone_length = sum(float(zone["length_m"]) for zone in zones) or 1.0
    target_rise = max(target_exit - current_surface, 0.0)
    max_rise_rate = float(process["max_rise_rate_c_per_min"])
    max_delta = float(process["max_core_surface_delta_c"])
    step_speed = float(process["step_length_m"]) / max(float(process["step_cycle_s"]), 1.0)
    conductivity_factor = clamp(float(billet["conductivity"]) / 32.0, 0.75, 1.35)
    thickness_factor = clamp(0.12 / max(float(billet["thickness_m"]), 0.06), 0.7, 1.4)

    zone_results: list[ZoneResult] = []
    objective_energy = 0.0
    objective_oxidation = 0.0

    for index, zone in enumerate(zones, start=1):
        zone_length = float(zone["length_m"])
        base_setpoint = float(zone["furnace_temp_c"])
        htc = float(zone["heat_transfer_coeff"])
        residence_time_s = zone_length / max(step_speed, 0.01)
        zone_target = process["entry_temp_c"] + target_rise * (sum(float(z["length_m"]) for z in zones[:index]) / total_zone_length)
        if optimize:
            correction = (zone_target - (current_surface + current_core) / 2.0) * 0.18
            setpoint = clamp(base_setpoint + correction, base_setpoint - 35.0, base_setpoint + 55.0)
        else:
            setpoint = base_setpoint

        heat_gain = (setpoint - current_surface) * (0.12 + htc / 1500.0) * conductivity_factor * thickness_factor
        next_surface = current_surface + heat_gain
        core_follow = clamp((next_surface - current_core) * (0.46 + conductivity_factor * 0.12), 0.0, max_delta)
        next_core = current_core + core_follow
        average_temp = (next_surface + next_core) / 2.0
        rise_rate = max((average_temp - ((current_surface + current_core) / 2.0)) / max(residence_time_s / 60.0, 1e-6), 0.0)
        if rise_rate > max_rise_rate:
            over_limit = rise_rate - max_rise_rate
            setpoint -= over_limit * 0.85
            next_surface -= over_limit * 0.72
            next_core -= over_limit * 0.38
            average_temp = (next_surface + next_core) / 2.0
            rise_rate = max_rise_rate

        objective_energy += max(setpoint - average_temp, 0.0) * zone_length
        objective_oxidation += max(setpoint - 1100.0, 0.0) * zone_length / 100.0

        zone_results.append(
            ZoneResult(
                zone_name=str(zone["name"]),
                residence_time_s=round2(residence_time_s),
                furnace_setpoint_c=round2(setpoint),
                surface_temp_c=round2(next_surface),
                core_temp_c=round2(next_core),
                average_temp_c=round2(average_temp),
                temp_rise_rate_c_per_min=round2(rise_rate),
            )
        )
        current_surface = next_surface
        current_core = next_core

    exit_avg = (current_surface + current_core) / 2.0
    exit_delta = current_surface - current_core
    target_deviation = exit_avg - target_exit
    quality_penalty = abs(target_deviation) * 2.5 + max(abs(exit_delta) - max_delta, 0.0) * 1.8
    objective_total = quality_penalty + objective_energy / 50.0 + objective_oxidation

    return {
        "model_name": "步进炉二级计算离线模型",
        "file_name": "walking_beam_level2_offline.py",
        "furnace_type": case_data["furnace_type"],
        "model_level": case_data["model_level"],
        "model_mode": case_data["model_mode"],
        "operation_mode": "optimize" if optimize else "simulate",
        "optimized_setpoints_c": {result.zone_name: result.furnace_setpoint_c for result in zone_results},
        "zone_results": [result.__dict__ for result in zone_results],
        "exit_temperatures": {
            "surface_temp_c": round2(current_surface),
            "core_temp_c": round2(current_core),
            "average_temp_c": round2(exit_avg),
        },
        "target_deviation_c": round2(target_deviation),
        "core_surface_delta_c": round2(exit_delta),
        "max_rise_rate_c_per_min": round2(max((result.temp_rise_rate_c_per_min for result in zone_results), default=0.0)),
        "energy_proxy": round2(objective_energy),
        "oxidation_proxy": round2(objective_oxidation),
        "objective_value": round2(objective_total),
        "input_summary": {
            "zone_count": len(zone_results),
            "billet_width_m": billet["width_m"],
            "billet_thickness_m": billet["thickness_m"],
            "entry_temp_c": process["entry_temp_c"],
            "target_exit_temp_c": process["target_exit_temp_c"],
        },
    }


def run(context: dict) -> dict:
    case_data = merge_case(context)
    optimize = str((context.get("run_options") or {}).get("mode", "optimize")).lower() != "simulate"
    outputs = simulate(case_data, optimize=optimize)
    return {
        "status": "success",
        "outputs": outputs,
        "logs": [
            f"loaded model file: {outputs['file_name']}",
            f"mode: {outputs['operation_mode']}",
            f"zone count: {outputs['input_summary']['zone_count']}",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="walking beam level2 offline model")
    parser.add_argument("case_path", nargs="?", help="json case path")
    parser.add_argument("--mode", choices=["simulate", "optimize"], default="optimize")
    args = parser.parse_args()

    if args.case_path:
        with open(args.case_path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        context = {"model_payload": payload, "run_options": {"mode": args.mode}}
    else:
        raw = sys.stdin.read().strip()
        context = json.loads(raw) if raw else {}
        context.setdefault("run_options", {})
        context["run_options"].setdefault("mode", args.mode)

    result = run(context)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
