# 05 执行器协议规格

## 1. 请求协议

```json
{
  "execution_id": "EXEC-20260604-0001",
  "template_code": "walking_beam_furnace_temp_profile_v1",
  "template_version": "1.0.0",
  "mode": "simulate",
  "inputs": {},
  "files": [],
  "context": {
    "project_code": "PRJ-2026-001",
    "item_code": "ITEM-WBF-001"
  }
}
```

## 2. 成功响应

```json
{
  "success": true,
  "feasible": true,
  "outputs": {
    "final_average_temp_c": 1181.2,
    "surface_core_delta_c": 3.8
  },
  "warnings": [],
  "errors": [],
  "charts": [],
  "logs": ["execution completed"]
}
```

## 3. 不可行响应

```json
{
  "success": true,
  "feasible": false,
  "outputs": {
    "surface_core_delta_c": 12.5
  },
  "warnings": [
    {
      "code": "CONSTRAINT_EXCEEDED",
      "message": "表里温差超过 5 ℃"
    }
  ],
  "errors": [],
  "suggestions": ["延长停留时间", "提高均热段炉温"]
}
```

## 4. 失败响应

```json
{
  "success": false,
  "feasible": false,
  "outputs": {},
  "warnings": [],
  "errors": [
    {
      "code": "PARAM_INVALID",
      "message": "target_discharge_temp_c 超出范围"
    }
  ],
  "logs": []
}
```

## 5. 执行要求

1. V1.0 只实现 Python 执行器。
2. 执行器不得直接写数据库，由服务层保存记录。
3. 所有结果必须可 JSON 序列化。
4. 所有错误必须使用统一错误结构。
5. 执行前后必须保存快照。
