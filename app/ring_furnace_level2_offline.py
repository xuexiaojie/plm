from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RingZoneResult:
    zone_name: str
    zone_angle_deg: float
    residence_time_s: float
    hearth_rotation_deg_per_min: float
    furnace_setpoint_c: float
    outer_surface_temp_c: float
    inner_surface_temp_c: float
    core_temp_c: float
    average_temp_c: float
    temp_rise_rate_c_per_min: float


DEFAULT_CASE = {
    "billet": {
        "width_m": 0.18,
        "thickness_m": 0.12,
        "length_m": 1.2,
        "density": 7850.0,
        "specific_heat": 690.0,
        "conductivity": 34.0,
        "emissivity": 0.80,
    },
    "process": {
        "entry_temp_c": 30.0,
        "target_exit_temp_c": 920.0,
        "max_core_surface_delta_c": 5.0,
        "max_rise_rate_c_per_min": 40.0,
        "rotation_period_min": 72.0,
        "charge_angle_deg": 18.0,
        "discharge_angle_deg": 342.0,
        "available_heating_angle_deg": 324.0,
    },
    "zones": [
        {"name": "preheat_arc", "zone_angle_deg": 80.0, "furnace_temp_c": 980.0, "radiation_factor": 0.82},
        {"name": "heating_arc_1", "zone_angle_deg": 92.0, "furnace_temp_c": 1180.0, "radiation_factor": 0.92},
        {"name": "heating_arc_2", "zone_angle_deg": 86.0, "furnace_temp_c": 1280.0, "radiation_factor": 0.96},
        {"name": "soaking_arc", "zone_angle_deg": 66.0, "furnace_temp_c": 1120.0, "radiation_factor": 0.88},
    ],
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round2(value: float) -> float:
    return round(value, 2)


def merge_case(context: dict) -> dict:
    payload = context.get("model_payload") or {}
    billet = dict(DEFAULT_CASE["billet"])
    process = dict(DEFAULT_CASE["process"])
    zones = [dict(zone) for zone in DEFAULT_CASE["zones"]]
    billet.update(payload.get("billet") or {})
    process.update(payload.get("process") or {})
    if isinstance(payload.get("zones"), list) and payload["zones"]:
        zones = [dict(zone) for zone in payload["zones"]]
    return {
        "billet": billet,
        "process": process,
        "zones": zones,
        "furnace_type": (context.get("node_metadata") or {}).get("furnace_type", "环形炉"),
        "model_level": (context.get("node_metadata") or {}).get("model_level", "二级"),
        "model_mode": (context.get("node_metadata") or {}).get("model_mode", "offline"),
    }


def simulate(case_data: dict, optimize: bool) -> dict:
    billet = case_data["billet"]
    process = case_data["process"]
    zones = case_data["zones"]
    current_outer = float(process["entry_temp_c"])
    current_inner = current_outer
    current_core = current_outer
    target_exit = float(process["target_exit_temp_c"])
    max_delta = float(process["max_core_surface_delta_c"])
    max_rise_rate = float(process["max_rise_rate_c_per_min"])
    available_angle = float(process.get("available_heating_angle_deg", 324.0))
    rotation_period_min = max(float(process.get("rotation_period_min", 72.0)), 1.0)
    base_rotation_speed = available_angle / rotation_period_min
    conductivity_factor = clamp(float(billet["conductivity"]) / 34.0, 0.75, 1.35)
    thickness_factor = clamp(0.12 / max(float(billet["thickness_m"]), 0.05), 0.7, 1.45)
    emissivity_factor = clamp(float(billet["emissivity"]) / 0.80, 0.75, 1.25)
    total_angle = sum(float(zone.get("zone_angle_deg", zone.get("length_m", 1.0))) for zone in zones) or 1.0
    target_rise = max(target_exit - current_core, 0.0)
    zone_results: list[RingZoneResult] = []
    energy_proxy = 0.0
    oxidation_proxy = 0.0
    rotation_uniformity_proxy = 0.0

    for index, zone in enumerate(zones, start=1):
        zone_angle = float(zone.get("zone_angle_deg", zone.get("length_m", 1.0)))
        base_setpoint = float(zone["furnace_temp_c"])
        radiation_factor = float(zone.get("radiation_factor", zone.get("heat_transfer_coeff", 180.0) / 220.0))
        progress = sum(float(item.get("zone_angle_deg", item.get("length_m", 1.0))) for item in zones[:index]) / total_angle
        zone_target = float(process["entry_temp_c"]) + target_rise * progress
        if optimize:
            correction = (zone_target - (current_outer + current_inner + current_core) / 3.0) * 0.15
            setpoint = clamp(base_setpoint + correction, base_setpoint - 40.0, base_setpoint + 60.0)
            speed = clamp(base_rotation_speed * (1.02 - progress * 0.08), base_rotation_speed * 0.82, base_rotation_speed * 1.08)
        else:
            setpoint = base_setpoint
            speed = base_rotation_speed
        residence_time_s = zone_angle / max(speed, 1e-6) * 60.0
        exchange = (0.11 + radiation_factor * 0.10) * conductivity_factor * thickness_factor * emissivity_factor
        outer_gain = (setpoint - current_outer) * exchange
        inner_gain = (setpoint - current_inner) * exchange * 0.94
        next_outer = current_outer + outer_gain
        next_inner = current_inner + inner_gain
        surface_avg = (next_outer + next_inner) / 2.0
        next_core = current_core + clamp((surface_avg - current_core) * (0.48 + conductivity_factor * 0.10), 0.0, max_delta)
        average_temp = (next_outer + next_inner + next_core) / 3.0
        rise_rate = max((average_temp - ((current_outer + current_inner + current_core) / 3.0)) / max(residence_time_s / 60.0, 1e-6), 0.0)
        if rise_rate > max_rise_rate:
            over_limit = rise_rate - max_rise_rate
            setpoint -= over_limit * 0.76
            next_outer -= over_limit * 0.58
            next_inner -= over_limit * 0.55
            next_core -= over_limit * 0.34
            average_temp = (next_outer + next_inner + next_core) / 3.0
            rise_rate = max_rise_rate
        hottest_surface = max(next_outer, next_inner)
        if hottest_surface - next_core > max_delta:
            next_core = hottest_surface - max_delta
            average_temp = (next_outer + next_inner + next_core) / 3.0

        energy_proxy += max(setpoint - average_temp, 0.0) * zone_angle * radiation_factor / 10.0
        oxidation_proxy += max(setpoint - 1080.0, 0.0) * zone_angle / 900.0
        rotation_uniformity_proxy += abs(next_outer - next_inner) * zone_angle / 100.0
        zone_results.append(
            RingZoneResult(
                zone_name=str(zone["name"]),
                zone_angle_deg=round2(zone_angle),
                residence_time_s=round2(residence_time_s),
                hearth_rotation_deg_per_min=round2(speed),
                furnace_setpoint_c=round2(setpoint),
                outer_surface_temp_c=round2(next_outer),
                inner_surface_temp_c=round2(next_inner),
                core_temp_c=round2(next_core),
                average_temp_c=round2(average_temp),
                temp_rise_rate_c_per_min=round2(rise_rate),
            )
        )
        current_outer = next_outer
        current_inner = next_inner
        current_core = next_core

    exit_avg = (current_outer + current_inner + current_core) / 3.0
    hottest_surface = max(current_outer, current_inner)
    core_surface_delta = hottest_surface - current_core
    target_deviation = exit_avg - target_exit
    objective_value = abs(target_deviation) * 2.4 + max(core_surface_delta - max_delta, 0.0) * 2.0 + energy_proxy / 55.0 + oxidation_proxy + rotation_uniformity_proxy
    return {
        "model_name": "环形炉二级计算离线模型",
        "file_name": "ring_furnace_level2_offline.py",
        "furnace_type": case_data["furnace_type"],
        "model_level": case_data["model_level"],
        "model_mode": case_data["model_mode"],
        "operation_mode": "optimize" if optimize else "simulate",
        "optimized_setpoints_c": {result.zone_name: result.furnace_setpoint_c for result in zone_results},
        "optimized_rotation_speeds_deg_per_min": {result.zone_name: result.hearth_rotation_deg_per_min for result in zone_results},
        "zone_results": [result.__dict__ for result in zone_results],
        "exit_temperatures": {
            "surface_temp_c": round2(hottest_surface),
            "outer_surface_temp_c": round2(current_outer),
            "inner_surface_temp_c": round2(current_inner),
            "core_temp_c": round2(current_core),
            "average_temp_c": round2(exit_avg),
        },
        "target_deviation_c": round2(target_deviation),
        "core_surface_delta_c": round2(core_surface_delta),
        "max_rise_rate_c_per_min": round2(max((result.temp_rise_rate_c_per_min for result in zone_results), default=0.0)),
        "energy_proxy": round2(energy_proxy),
        "oxidation_proxy": round2(oxidation_proxy),
        "rotation_uniformity_proxy": round2(rotation_uniformity_proxy),
        "objective_value": round2(objective_value),
        "input_summary": {
            "zone_count": len(zone_results),
            "rotation_period_min": process.get("rotation_period_min"),
            "available_heating_angle_deg": process.get("available_heating_angle_deg"),
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
