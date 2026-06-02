from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RollerZoneResult:
    zone_name: str
    residence_time_s: float
    roller_speed_m_per_min: float
    furnace_setpoint_c: float
    top_surface_temp_c: float
    bottom_surface_temp_c: float
    core_temp_c: float
    average_temp_c: float
    temp_rise_rate_c_per_min: float


DEFAULT_CASE = {
    "plate": {
        "width_m": 2.0,
        "thickness_m": 0.08,
        "length_m": 8.0,
        "density": 7850.0,
        "specific_heat": 700.0,
        "conductivity": 36.0,
        "emissivity": 0.78,
    },
    "process": {
        "entry_temp_c": 30.0,
        "target_exit_temp_c": 920.0,
        "max_core_surface_delta_c": 5.0,
        "max_rise_rate_c_per_min": 38.0,
        "roller_speed_m_per_min": 0.28,
        "min_roller_speed_m_per_min": 0.12,
        "operation_mode": "continuous",
    },
    "zones": [
        {"name": "preheat", "length_m": 18.0, "furnace_temp_c": 980.0, "radiant_tube_factor": 0.84},
        {"name": "heating_1", "length_m": 22.0, "furnace_temp_c": 1180.0, "radiant_tube_factor": 0.92},
        {"name": "heating_2", "length_m": 20.0, "furnace_temp_c": 1260.0, "radiant_tube_factor": 0.96},
        {"name": "soaking", "length_m": 16.0, "furnace_temp_c": 1120.0, "radiant_tube_factor": 0.88},
    ],
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round2(value: float) -> float:
    return round(value, 2)


def merge_case(context: dict) -> dict:
    payload = context.get("model_payload") or {}
    plate = dict(DEFAULT_CASE["plate"])
    process = dict(DEFAULT_CASE["process"])
    zones = [dict(zone) for zone in DEFAULT_CASE["zones"]]

    plate.update(payload.get("plate") or payload.get("billet") or {})
    process.update(payload.get("process") or {})
    if isinstance(payload.get("zones"), list) and payload["zones"]:
        zones = [dict(zone) for zone in payload["zones"]]

    return {
        "plate": plate,
        "process": process,
        "zones": zones,
        "furnace_type": (context.get("node_metadata") or {}).get("furnace_type", "辊底炉"),
        "model_level": (context.get("node_metadata") or {}).get("model_level", "二级"),
        "model_mode": (context.get("node_metadata") or {}).get("model_mode", "offline"),
    }


def simulate(case_data: dict, optimize: bool) -> dict:
    plate = case_data["plate"]
    process = case_data["process"]
    zones = case_data["zones"]
    current_top = float(process["entry_temp_c"])
    current_bottom = current_top
    current_core = current_top
    target_exit = float(process["target_exit_temp_c"])
    max_delta = float(process["max_core_surface_delta_c"])
    max_rise_rate = float(process["max_rise_rate_c_per_min"])
    base_speed = float(process.get("roller_speed_m_per_min", 0.28))
    min_speed = float(process.get("min_roller_speed_m_per_min", 0.12))
    operation_mode = str(process.get("operation_mode", "continuous"))
    speed = max(base_speed, min_speed)
    if operation_mode == "swing":
        speed *= 0.72

    conductivity_factor = clamp(float(plate["conductivity"]) / 36.0, 0.75, 1.35)
    thickness_factor = clamp(0.08 / max(float(plate["thickness_m"]), 0.04), 0.65, 1.45)
    emissivity_factor = clamp(float(plate["emissivity"]) / 0.78, 0.75, 1.25)
    total_length = sum(float(zone["length_m"]) for zone in zones) or 1.0
    target_rise = max(target_exit - current_core, 0.0)
    zone_results: list[RollerZoneResult] = []
    energy_proxy = 0.0
    oxidation_proxy = 0.0
    roller_load_proxy = 0.0

    for index, zone in enumerate(zones, start=1):
        zone_length = float(zone["length_m"])
        base_setpoint = float(zone["furnace_temp_c"])
        radiant_factor = float(zone.get("radiant_tube_factor", zone.get("heat_transfer_coeff", 180.0) / 220.0))
        progress = sum(float(item["length_m"]) for item in zones[:index]) / total_length
        zone_target = float(process["entry_temp_c"]) + target_rise * progress
        if optimize:
            correction = (zone_target - (current_top + current_bottom + current_core) / 3.0) * 0.16
            setpoint = clamp(base_setpoint + correction, base_setpoint - 45.0, base_setpoint + 65.0)
            speed_factor = clamp((target_exit - current_core) / max(target_rise, 1.0), 0.72, 1.08)
            zone_speed = max(min_speed, speed * speed_factor)
        else:
            setpoint = base_setpoint
            zone_speed = speed

        residence_time_s = zone_length / max(zone_speed / 60.0, 1e-6)
        exchange = (0.10 + radiant_factor * 0.115) * conductivity_factor * thickness_factor * emissivity_factor
        top_gain = (setpoint - current_top) * exchange
        roller_shadow = 0.92 if operation_mode == "continuous" else 0.98
        bottom_gain = (setpoint - current_bottom) * exchange * roller_shadow
        next_top = current_top + top_gain
        next_bottom = current_bottom + bottom_gain
        surface_average = (next_top + next_bottom) / 2.0
        next_core = current_core + clamp((surface_average - current_core) * (0.50 + conductivity_factor * 0.10), 0.0, max_delta)
        average_temp = (next_top + next_bottom + next_core) / 3.0
        rise_rate = max((average_temp - ((current_top + current_bottom + current_core) / 3.0)) / max(residence_time_s / 60.0, 1e-6), 0.0)
        if rise_rate > max_rise_rate:
            over_limit = rise_rate - max_rise_rate
            setpoint -= over_limit * 0.78
            next_top -= over_limit * 0.62
            next_bottom -= over_limit * 0.58
            next_core -= over_limit * 0.35
            average_temp = (next_top + next_bottom + next_core) / 3.0
            rise_rate = max_rise_rate

        hottest_surface = max(next_top, next_bottom)
        if hottest_surface - next_core > max_delta:
            next_core = hottest_surface - max_delta
            average_temp = (next_top + next_bottom + next_core) / 3.0

        energy_proxy += max(setpoint - average_temp, 0.0) * zone_length * radiant_factor
        oxidation_proxy += max(setpoint - 1050.0, 0.0) * zone_length / 120.0
        roller_load_proxy += residence_time_s * max(float(plate["width_m"]), 0.1) * max(float(plate["thickness_m"]), 0.01) / 100.0
        zone_results.append(
            RollerZoneResult(
                zone_name=str(zone["name"]),
                residence_time_s=round2(residence_time_s),
                roller_speed_m_per_min=round2(zone_speed),
                furnace_setpoint_c=round2(setpoint),
                top_surface_temp_c=round2(next_top),
                bottom_surface_temp_c=round2(next_bottom),
                core_temp_c=round2(next_core),
                average_temp_c=round2(average_temp),
                temp_rise_rate_c_per_min=round2(rise_rate),
            )
        )
        current_top = next_top
        current_bottom = next_bottom
        current_core = next_core

    exit_avg = (current_top + current_bottom + current_core) / 3.0
    hottest_surface = max(current_top, current_bottom)
    core_surface_delta = hottest_surface - current_core
    target_deviation = exit_avg - target_exit
    objective_value = abs(target_deviation) * 2.4 + max(core_surface_delta - max_delta, 0.0) * 2.0 + energy_proxy / 60.0 + oxidation_proxy + roller_load_proxy
    return {
        "model_name": "辊底炉二级计算离线模型",
        "file_name": "roller_hearth_level2_offline.py",
        "furnace_type": case_data["furnace_type"],
        "model_level": case_data["model_level"],
        "model_mode": case_data["model_mode"],
        "operation_mode": "optimize" if optimize else "simulate",
        "roller_operation_mode": operation_mode,
        "optimized_setpoints_c": {result.zone_name: result.furnace_setpoint_c for result in zone_results},
        "optimized_roller_speeds_m_per_min": {result.zone_name: result.roller_speed_m_per_min for result in zone_results},
        "zone_results": [result.__dict__ for result in zone_results],
        "exit_temperatures": {
            "surface_temp_c": round2(hottest_surface),
            "top_surface_temp_c": round2(current_top),
            "bottom_surface_temp_c": round2(current_bottom),
            "core_temp_c": round2(current_core),
            "average_temp_c": round2(exit_avg),
        },
        "target_deviation_c": round2(target_deviation),
        "core_surface_delta_c": round2(core_surface_delta),
        "max_rise_rate_c_per_min": round2(max((result.temp_rise_rate_c_per_min for result in zone_results), default=0.0)),
        "energy_proxy": round2(energy_proxy),
        "oxidation_proxy": round2(oxidation_proxy),
        "roller_load_proxy": round2(roller_load_proxy),
        "objective_value": round2(objective_value),
        "input_summary": {
            "zone_count": len(zone_results),
            "plate_width_m": plate["width_m"],
            "plate_thickness_m": plate["thickness_m"],
            "target_exit_temp_c": process["target_exit_temp_c"],
            "roller_speed_m_per_min": process.get("roller_speed_m_per_min"),
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
            f"roller mode: {outputs['roller_operation_mode']}",
        ],
    }
