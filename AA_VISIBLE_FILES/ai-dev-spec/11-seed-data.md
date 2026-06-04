# 11 初始化数据规格

## 1. 用户

| username | role | 说明 |
|---|---|---|
| `admin` | 系统管理员 | 全权限 |
| `engineer` | 普通计算人员 | 建模与执行 |
| `reviewer` | 审核人 | 审批 |
| `readonly` | 只读用户 | 查看 |

## 2. 角色

1. 普通计算人员
2. 审核人
3. 模板管理员
4. 算法维护人员
5. 系统管理员
6. 只读用户

## 3. 字典

### 3.1 furnace_type

1. `walking_beam_furnace`
2. `roller_hearth_furnace`
3. `ring_furnace`

### 3.2 execution_status

1. `PENDING`
2. `RUNNING`
3. `SUCCESS`
4. `FAILED`
5. `CANCELLED`

### 3.3 approval_status

1. `DRAFT`
2. `SUBMITTED`
3. `RETURNED`
4. `APPROVED`
5. `ARCHIVED`
6. `CANCELLED`

## 4. 样例项目

```json
{
  "code": "PRJ-2026-001",
  "name": "1780 热轧产线工业炉样例项目",
  "owner_user_id": 2,
  "status": "ACTIVE"
}
```

## 5. 样例名目

1. `ITEM-WBF-001`：1 号步进炉设计校核。
2. `ITEM-RHF-001`：2 号辊底炉热处理复核。
3. `ITEM-RING-001`：环形炉炉温制度优化。

## 6. 样例模板

1. `walking_beam_furnace_temp_profile_v1`
2. `roller_hearth_furnace_temp_profile_v1`
3. `ring_furnace_temp_profile_v1`

## 7. 执行要求

1. seed 脚本必须幂等。
2. 编码字段已存在时更新，不重复插入。
3. seed 后可直接完成验收用例。
