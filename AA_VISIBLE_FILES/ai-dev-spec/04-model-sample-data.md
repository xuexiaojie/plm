# 04 模型样例数据规格

## 1. 判定规则

1. 默认表里温差约束：`surface_core_delta_c <= 5`。
2. 出炉温度误差建议范围：`abs(discharge_temp_error_c) <= 10`。
3. 不可行工况必须返回 `feasible=false`。
4. 输出数值允许误差：V1.0 Mock 模型允许相对误差 5%。

## 2. 梁式步进炉样例

### 2.1 正常工况

```json
{
  "material_type": "carbon_steel",
  "workpiece_thickness_mm": 180,
  "workpiece_width_mm": 1200,
  "workpiece_length_mm": 9000,
  "initial_temp_c": 25,
  "target_discharge_temp_c": 1180,
  "furnace_zone_count": 3,
  "zone_setpoints_c": [950, 1180, 1240],
  "residence_time_min": 180
}
```

预期：`feasible=true`，`final_average_temp_c` 在 1170 到 1190 之间，`surface_core_delta_c <= 5`。

### 2.2 边界工况

厚坯、短停留时间，预期接近约束上限。

### 2.3 不可行工况

停留时间小于 60 分钟，预期 `feasible=false` 并返回建议延长停留时间。

## 3. 辊底炉样例

### 3.1 正常工况

```json
{
  "material_type": "alloy_steel",
  "workpiece_thickness_mm": 60,
  "initial_temp_c": 25,
  "target_discharge_temp_c": 920,
  "furnace_zone_count": 4,
  "zone_setpoints_c": [650, 780, 900, 940],
  "residence_time_min": 90,
  "roller_speed_m_per_min": 0.35
}
```

预期：`feasible=true`，`final_average_temp_c` 在 910 到 930 之间。

### 3.2 边界工况

低合金钢、较高目标温度、较短停留时间。

### 3.3 不可行工况

辊速过快导致停留时间不足，返回降低辊速建议。

## 4. 环形炉样例

### 4.1 正常工况

```json
{
  "material_type": "carbon_steel",
  "workpiece_thickness_mm": 120,
  "initial_temp_c": 50,
  "target_discharge_temp_c": 1150,
  "furnace_zone_count": 5,
  "zone_setpoints_c": [850, 980, 1100, 1200, 1230],
  "residence_time_min": 150,
  "rotation_period_min": 6
}
```

预期：`feasible=true`，`final_average_temp_c` 在 1140 到 1160 之间。

### 4.2 边界工况

大截面工件、旋转周期偏短。

### 4.3 不可行工况

目标温度过高且停留时间不足，返回提高炉温或延长周期建议。
