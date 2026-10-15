# Phase 5-R3-R4 综合报告（信号恢复与 API 溯源）

**日期阶段：** Phase 5-R3-R4 收尾  
**HEAD 基线：** `6dfd107`（信号恢复更新）  
**论文方向：** Evolutionary Learning of Adaptive Search Strategies for Multi-objective LLM Agents

---

## 1. 执行摘要

1. DeepSeek API 曾出现 **HTTP 402 / 空 body**，期间完成全部离线目标审计与预算门禁改造。
2. API 恢复后补跑 horizon 诊断，**在 H=30 得到首个原生 `won=True` 成功**。
3. 正式实验模型为 **`deepseek-flash`**；`deepseek-v4-pro` 仅 1 次连通性探针，`deepseek-chat` 为历史旧名。
4. Efficiency / Robustness / Autonomy 三维经反例验证 **暂不可进论文主表**。

---

## 2. API 与模型溯源

| 模型 | 是否调用 | 用途 | 调用量 |
|------|----------|------|--------|
| **deepseek-flash** | ✅ 是 | 正式诊断 / horizon / 原生执行 | horizon 118+ 次 |
| deepseek-v4-pro | ✅ 是（仅探针） | 402 前故障隔离 | ~1 次 |
| deepseek-chat | 历史阶段 | Phase 4 旧配置 | 已废止 |
| deepseek-pro | ❌ 否 | 不存在于仓库 | 0 |

统一配置：`src/backend/base.py` → `DeepSeekBackend.model = "deepseek-flash"`，  
`thinking.type=disabled`，密钥仅 `DEEPSEEK_API_KEY`。

---

## 3. 原生环境与任务

| 项 | 值 |
|----|-----|
| 环境 | ALFWorld TextWorld（alfworld 0.4.2 / textworld 1.7.0，Docker） |
| 开发池 | valid_train，50 任务（`development_task_pool.json`） |
| 冻结测试 | valid_unseen，30 任务（`frozen_final_test_manifest.json`） |
| 已污染 | 2 个 vase→safe game ID（此前 pilot 使用） |

---

## 4. Horizon 诊断（DeepSeek，valid_train）

| Horizon | Success | Avg Steps | 终止主因 | 状态变化次数 |
|---------|---------|-----------|----------|--------------|
| 10 | 0/2 | 10 | max_steps | 18 |
| 20 | 0/2 | 20 | max_steps | 38 |
| **30** | **1/2** | 28.5 | 1 success + 1 budget | **55** |

**结论：** 5 步 pilot 的 0% 成功主要由 **horizon 过短** 造成；H=30 时官方 `won` 可达成，且无重复动作循环。

---

## 5. Objective 有效性（诊断级，未改论文定义）

| 目标 | 测量 | 是否可进主表 | 关键问题 |
|------|------|--------------|----------|
| Performance | env `won` | ✅ | 无 |
| Efficiency | steps+tokens | ❌ | 快失败效率 0.94 > 成功 0.54 |
| Cost | API $ | ⚠️ | 微实验动态范围小 |
| Robustness | perf×(1−stall) | ❌ | 与 performance 冗余 |
| Autonomy | 预算/停滞 | ❌ | 行为代理，需独立定义 |

---

## 6. 工程加固（本轮新增）

- `src/runtime/api_budget.py`：请求前原子预留、重试计费、estimated/actual tokens 分账
- `src/evaluation/progress_signals.py`：进展诊断 + 失败分类（不进 fitness）
- `src/evaluation/objective_diagnostics.py`：反例与候选公式（待 Planner 批准）
- Episode 隔离 / 游戏轮换 / goal 传递 / 预算耗尽硬停止（R3-R3→R3-R4）

---

## 7. 对算法主张的影响

| 命题 | 状态 |
|------|------|
| 原生环境可进化 | 链路成立（`ACCEPTED_SIGNAL_READY`） |
| PEEM 优于 NSGA-III | **未验证**（尚无等预算多种子原生对照） |
| PPEC 偏好有效 | 离线选择差异有证据；原生待跑 |
| 五目标完整可用 | **否**（3 项需协议升级） |

---

## 8. 建议下一步（待 Planner 批准）

1. **H=20–30、valid_train** 上做四方法等预算 pilot（RS / NSGA-III / +PEEM / +PPEC）。
2. 批准 Plan A 后重测 efficiency / robustness / autonoomy。
3. 方法冻结后再碰 frozen `valid_unseen` 测试清单。
4. 全程使用 `APICallGate` 硬预算，报告 API/tokens/$ 实数。

---

## 9. 状态

**`ACCEPTED_SIGNAL_READY`**

原生成功信号已恢复；算法优越性主张仍待公平对照实验。
