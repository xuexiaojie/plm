# 梁式步进炉二级离线模型

我直接实现了一个可运行的二级离线模型程序，主参考采用博士论文《步进梁加热炉炉温综合优化控制策略研究》，并按检索结果中常见的二级结构落地为代码：

- 钢坯温度预报模型
- 分区炉温优化设定模型

## 模型结构

程序文件：`walking_beam_level2_offline.py`

核心功能：

- 基于钢坯厚度方向一维非稳态导热的温度预报
- 引入温度相关等效比热和导热系数
- 按预热段、加热段、均热段分区计算驻留加热过程
- 构造理想平均温升曲线，约束各段钢温爬升过程
- 以出炉温度偏差、表里温差、加热速率、能耗代理项、氧化烧损代理项构造离线优化目标
- 采用两阶段坐标搜索生成各段炉温设定值

## 输入文件

示例：`example_case.json`

包含两部分：

- `billet`：钢坯尺寸、物性、目标出炉温度
- `furnace`：步距、步进周期、各区段长度与初始炉温设定值

## 运行方式

```bash
python3 walking_beam_level2_offline.py example_case.json --mode optimize
```

启动本地 Web 预览：

```bash
python3 app_server.py
```

仅做仿真：

```bash
python3 walking_beam_level2_offline.py example_case.json --mode simulate
```

## 输出说明

程序输出 JSON，主要字段包括：

- `final_surface_temp_c`：出炉表面温度
- `final_core_temp_c`：出炉心部温度
- `final_average_temp_c`：出炉平均温度
- `discharge_temp_error_c`：相对目标出炉温度偏差
- `surface_core_delta_c`：断面表里温差
- `max_heating_rate_c_per_min`：各段平均升温速率中的最大值
- `zone_setpoints_c`：优化后的各段炉温设定值
- `zone_snapshots`：各段出口钢温、停留时间、平均升温速率、目标钢温

## 工程说明

这个版本已经具备完整代码生成和离线求解能力，继续工程化时可扩展：

- 接入钢坯跟踪数据
- 加入钢种相关物性随温度变化
- 引入更细的辐射换热与黑度模型
- 替换当前坐标搜索为 SQP、PSO 或滚动优化算法
