# 08 报告与审批规格

## 1. 审批状态

1. `DRAFT`
2. `SUBMITTED`
3. `RETURNED`
4. `APPROVED`
5. `ARCHIVED`
6. `CANCELLED`

## 2. 审批流转

| from | action | to | 角色 |
|---|---|---|---|
| DRAFT | submit | SUBMITTED | 普通计算人员 |
| SUBMITTED | approve | APPROVED | 审核人 |
| SUBMITTED | return | RETURNED | 审核人 |
| RETURNED | submit | SUBMITTED | 普通计算人员 |
| APPROVED | archive | ARCHIVED | 系统管理员 |
| DRAFT | cancel | CANCELLED | 普通计算人员 |

## 3. 报告状态

| 状态 | 说明 | 水印 | 编号 |
|---|---|---|---|
| DRAFT | 执行后生成 | 草稿 | 无正式编号 |
| SUBMITTED | 提交审批后生成 | 待审 | 无正式编号 |
| OFFICIAL | 审批通过后生成 | 无 | `RPT-{yyyyMMdd}-{sequence}` |
| ARCHIVED | 归档锁定 | 归档 | 保留正式编号 |

## 4. 报告内容

1. 项目信息。
2. 名目信息。
3. 炉型和模板信息。
4. 输入参数摘要。
5. 输出结果摘要。
6. 约束判定。
7. 警告和错误。
8. 审批记录。
9. 报告版本。
10. 生成时间。

## 5. 下载权限

1. 草稿报告：创建人、管理员可下载。
2. 待审报告：创建人、审核人、管理员可下载。
3. 正式报告：授权用户可下载。
4. 归档报告：只读用户可查看，下载按授权控制。
