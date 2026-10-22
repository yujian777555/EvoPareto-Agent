# R354_R11_HANDOFF

## 1. Git
- **BASE_COMMIT:** `c1be57a60340bcc9f8762f03b8e8965d6800237f`
- **RESULT_COMMIT:** `1aedac71ff7ab0e2a076eb33695556ded5052e26`
- **BRANCH:** `planner/r354-r11-runtime-gates`
- **REMOTE_SYNC:** origin/planner/r354-r11-runtime-gates 已同步
- **WORKTREE_STATUS:** clean after commit

## 2. 修改文件

| 文件 | 目的 |
|------|------|
| `scripts/level3_pilot_r4/run_micro_r354.py` | Task A/B/C/D 修复 |
| `tests/baseline_first/test_r354_r11_runtime_order.py` | 新增 R1.1 回归（22 测试） |
| `docs/level3_pilot_r4_micro_r354/R354_R11_HANDOFF.md` | 本交接 |

## 3. 修复对照

### Task A — acc() 覆盖
- **问题:** `main()` 内 `acc()` 覆盖模块级严格版本；仅排除 `skipped`。
- **修复:** 删除内部定义；统一模块级 `classify_row()` + `is_valid_eval()` + `acc(rows, expected_n)`。
- **无效记录不进分母:** 执行失败/哈希不匹配/解析失败/跳过/缺失 → `acc` 返回 `None`。
- **测试:** `test_r354_r11_runtime_order.py::TestAccStrict`（10 场景）、`TestClassify`。

### Task B — 静态预检前移
- **问题:** `preflight_runtime()` 在 Dev/Confirm 之后调用。
- **修复:** 新增 `preflight_static()` 在**任何请求前**执行（含 base SHA 重算、集合互斥、历史排除、输出目录）；真实模式另有 `check_real_authorization()`。
- **顺序:** 静态预检 → 授权门禁 → 输出目录 → Dev → Dev 完整性 → 反馈生成 → A/O 一致性 → Confirm。
- **测试:** `TestStaticPreflight`（train SHA / base SHA 重算 / text mismatch / set overlap）。

### Task C — 授权门禁
- **问题:** `if not args.mock: return 3` 无条件阻断。
- **修复:** `check_real_authorization()` fail-closed 校验协议/模型/确认集 SHA/代码版本/请求与费用上限/状态。
- **本轮真实 HTTP = 0**；Mock 证据不得标为 REAL_MODEL。

### Task D — 预算与完整性
- `paired()` 现核验 **task_id 一一对应**（非仅长度）。
- Holm：缺失任一必需比较标记 `MULTIPLE_COMPARISONS_INCOMPLETE`。
- `experiment_complete` 增加 `holm_complete` 条件。
- `NO_USABLE_FEEDBACK` → 不伪造 A/O，不跑 Confirm，返回码 7。

## 4. 测试结果

| 套件 | 通过 | 失败 |
|------|------|------|
| **R1.1 新增** `test_r354_r11_runtime_order.py` | **22** | 0 |
| R3.5.4 mechanism | 7 | 0 |
| R3.5.4 R1 validity | 11 | **1**（预存） |
| R3.5.3 runtime | 17 | **1**（预存） |
| R3.5.2 gates | 19 | **1**（预存） |
| auth/budget/hard_budget | 58 | 0 |

**3 个预存失败** 在冻结基线 `c1be57a` 上同样失败（已用 `git stash` 对照验证）：
`test_preflight_tamper_zero_http`、`test_preflight_index_mapping`、`test_preflight_detects_hash_tamper`。

原因：`taskset_r354_manifest.json` 的 `train_sha256=17f347dc…` 与实际
`gsm8k_train_official.jsonl` 的 `232fb47f…` **不一致**（预存数据问题）。
新旧预检均正确检测该不一致。**未修改冻结数据。**

## 5. 调用顺序
1. 静态预检（零 HTTP）
2. 授权门禁（真实模式）
3. 输出目录检查
4. Dev B 评估
5. Dev 完整性 + 有效反馈过滤
6. A/O 构造 + 一致性检查
7. Confirm 评估
8. 统计 + Holm 完整性 + experiment_complete

## 6. 真实 HTTP
**0**（本轮仅 Mock/离线）。

## 7. 历史完整性
- R3.5.3 历史结果目录未改动
- 冻结任务集文件未改动
- 授权账本未创建/修改

## 8. 未解决阻塞
**BLOCKER-1:** `taskset_r354_manifest.json` 的 `train_sha256` 与 `gsm8k_train_official.jsonl` 实际 SHA 不符。影响 3 个既有测试；不影响本轮新增测试。需 Planner 决定是更新 manifest 还是替换 train 文件。**不得静默修复。**

## 9. 声明
**本轮只完成代码与模拟验证，不构成 R3.5.4 真实机制实验结果。**
