# 03 计算模板 Schema 规格

## 1. 模板主结构

```json
{
  "code": "walking_beam_furnace_temp_profile_v1",
  "name": "梁式步进炉升温计算",
  "category": "传热升温",
  "step_type": "temp_profile",
  "furnace_type": "walking_beam_furnace",
  "version": "1.0.0",
  "executor_type": "python",
  "entrypoint": "app.models.walking_beam:run",
  "input_fields": [],
  "output_fields": [],
  "report_template_code": "standard_calc_report_v1",
  "workflow_type": "standard_approval",
  "status": "ACTIVE",
  "formula_source": "待专业校核",
  "applicable_scope": "V1.0 演示模型"
}
```

## 2. 输入字段结构

```json
{
  "code": "target_discharge_temp_c",
  "name": "目标出炉温度",
  "data_type": "number",
  "unit": "℃",
  "default_value": 1180,
  "required": true,
  "min": 800,
  "max": 1350,
  "precision": 1,
  "source": "user_input",
  "help_text": "目标平均出炉温度",
  "compare_enabled": true
}
```

## 3. 输出字段结构

```json
{
  "code": "surface_core_delta_c",
  "name": "表里温差",
  "unit": "℃",
  "data_type": "number",
  "precision": 2,
  "report_enabled": true,
  "compare_enabled": true,
  "chart_enabled": true,
  "normal_range": {
    "max": 5
  }
}
```

## 4. 首批模板

| code | name | furnace_type | step_type |
|---|---|---|---|
| `walking_beam_furnace_temp_profile_v1` | 梁式步进炉升温计算 | `walking_beam_furnace` | `temp_profile` |
| `roller_hearth_furnace_temp_profile_v1` | 辊底炉热处理升温计算 | `roller_hearth_furnace` | `temp_profile` |
| `ring_furnace_temp_profile_v1` | 环形炉炉温制度计算 | `ring_furnace` | `temp_profile` |

## 5. 通用输入字段

1. `material_type`
2. `workpiece_thickness_mm`
3. `workpiece_width_mm`
4. `workpiece_length_mm`
5. `initial_temp_c`
6. `target_discharge_temp_c`
7. `furnace_zone_count`
8. `zone_setpoints_c`
9. `residence_time_min`

## 6. 通用输出字段

1. `final_surface_temp_c`
2. `final_core_temp_c`
3. `final_average_temp_c`
4. `surface_core_delta_c`
5. `discharge_temp_error_c`
6. `max_heating_rate_c_per_min`
7. `feasible`
8. `constraint_violations`
9. `suggestions`
