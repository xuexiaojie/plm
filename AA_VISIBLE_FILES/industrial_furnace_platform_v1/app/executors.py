from __future__ import annotations

from typing import Any

from app.schemas import ExecutorResponse


def run_template(template_code: str, inputs: dict[str, Any]) -> ExecutorResponse:
    if template_code.startswith("walking_beam_furnace"):
        return _run_temperature_profile(inputs, furnace_label="步进炉")
    if template_code.startswith("roller_hearth_furnace"):
        return _run_temperature_profile(inputs, furnace_label="辊底炉")
    if template_code.startswith("ring_furnace"):
        return _run_temperature_profile(inputs, furnace_label="环形炉")
    return ExecutorResponse(
        success=False,
        feasible=False,
        errors=[{"code": "TEMPLATE_NOT_FOUND", "message": f"未知模板 {template_code}"}],
    )


def _run_temperature_profile(inputs: dict[str, Any], furnace_label: str) -> ExecutorResponse:
    required = ["workpiece_thickness_mm", "initial_temp_c", "target_discharge_temp_c", "residence_time_min"]
    missing = [field for field in required if field not in inputs]
    if missing:
        return ExecutorResponse(
            success=False,
            feasible=False,
            errors=[{"code": "PARAM_INVALID", "message": f"缺少参数: {', '.join(missing)}"}],
        )

    thickness = float(inputs["workpiece_thickness_mm"])
    initial = float(inputs["initial_temp_c"])
    target = float(inputs["target_discharge_temp_c"])
    residence = float(inputs["residence_time_min"])

    if target < 500 or target > 1400 or residence <= 0 or thickness <= 0:
        return ExecutorResponse(
            success=False,
            feasible=False,
            errors=[{"code": "PARAM_INVALID", "message": "目标温度、厚度或停留时间超出允许范围"}],
        )

    heat_factor = min(1.08, residence / max(60.0, thickness * 0.8))
    final_average = initial + (target - initial) * min(1.0, heat_factor)
    temp_error = final_average - target
    delta = max(1.5, thickness / max(residence, 1.0) * 3.0)
    feasible = abs(temp_error) <= 10 and delta <= 5
    warnings = []
    suggestions = []
    if not feasible:
        warnings.append(
            {
                "code": "CONSTRAINT_EXCEEDED",
                "message": "出炉温度或表里温差约束未满足",
            }
        )
        suggestions.extend(["延长停留时间", "优化分区炉温", "降低装炉节奏"])

    outputs = {
        "final_surface_temp_c": round(final_average + delta / 2, 2),
        "final_core_temp_c": round(final_average - delta / 2, 2),
        "final_average_temp_c": round(final_average, 2),
        "surface_core_delta_c": round(delta, 2),
        "discharge_temp_error_c": round(temp_error, 2),
        "max_heating_rate_c_per_min": round((final_average - initial) / residence, 3),
        "feasible": feasible,
        "constraint_violations": warnings,
        "suggestions": suggestions,
    }
    return ExecutorResponse(
        success=True,
        feasible=feasible,
        outputs=outputs,
        warnings=warnings,
        logs=[f"{furnace_label} V1.0 mock temperature profile completed"],
        suggestions=suggestions,
    )
