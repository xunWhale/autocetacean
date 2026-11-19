# AutoCetacean 项目进度

- 给谁用：AutoCetacean 确定性状态机 Agent 框架开发者。
- 解决什么：构建具备 Layer 1-5 约束、真实状态快照与滚动检查点、Gate 审批暂停/恢复、自愈重试与 CLI 闭环回放/拓扑渲染的确定性 Agent 运行时。
- 已完成（v0.2.0）：
  - 修复 `StateGraph.run()` 状态快照缺陷：在 schema 校验与 handler 执行前深拷贝 `state_before`，执行后深拷贝 `state_after`，`StepRecord.input_data` 保留前态，`metadata` 写入真实 `state_before`、`state_after`、`status`（含 `SUSPENDED` 兼容 `ReplayEngine`）与 `checkpoint_id`，失败步骤保留结构化 `violation` 与状态快照。
  - 更新 `Layer4LoopController.execute_with_retry()` 记录 `RETRY`/`HALT`/`SUCCESS` 及深拷贝前后态。
  - 在 `ExecutionContext` 新增 `reset_halt()` 与 `export_trace(path, format="jsonl")`；在 `StateGraph` 新增 `resume(context, approved=True, restore_checkpoint=False)` 与 `run(..., reset_halt=False)`；在 `CheckpointManager` 新增 `get_checkpoint(checkpoint_id)` 与 `load_from_dir()` 支持跨进程断点恢复。
  - 新增 `autocetacean run` CLI（支持 `StateGraph`、工厂函数、`(ctx)` 可调用目标、`--input`、`--trace-out`、`--checkpoint-dir`、`--approve-gates`、`--json`）与 `autocetacean graph --trace` 轨迹叠加渲染。
  - 更新 `examples/self_healing_agent.py` 展示 Layer 2 拦截 + `reset_halt()` + Layer 4 retry + Gate 暂停与 `resume` + trace 导出回放闭环；补充 10 项 v0.2.0 单元测试（全套 86 项全部通过），升级版本至 `0.2.0` 并完成 wheel 隔离环境验证与 `VERIFICATION_v0.2.md`。
- 下一步：如需支持异步节点与类型化状态 schema（`TypedDict`/dataclass 泛型约束，见 `docs/DEV_EXPERIENCE.md` FP-2），可在 v0.3.0 引入异步调度器与状态模型校验。
- 踩过的坑：
  - `StateGraph.run()` 过去使用 `dict(context.state)` 浅拷贝并在 `handler` 执行之后才调用 `record_step()`，导致嵌套字典被原地修改后污染 `input_data` 与前态快照；必须先 `copy.deepcopy` 抓取 `state_before`，再校验并执行，结束后再抓 `state_after`。
  - `examples/self_healing_agent.py` 若把 `checkpoint_mgr` 闭包进节点函数，`CLI --checkpoint-dir` 直接替换 `graph.checkpoints` 会导致节点内与图引擎持有的管理器分叉；通过更新现有 `graph.checkpoints.storage_dir` 可保证闭环一致落盘。
  - `StateGraph` 的条件边只保存 router callable，拓扑导出会从 router 返回表达式和代码常量恢复已注册节点，无法恢复时输出可见的 conditional route 占位节点。

## 2026-11-19（周三）

- 首屏改成"agent 把你仓库改坏了"的痛点 + 可跑命令，`guard` 成为入口，不再是抽象的 runtime（fa26dd5）
- 新增 `examples/git-is-not-enough.sh`：同一场混乱，git 恢复丢未跟踪文件与目录，guard 全部还原（a6a315c）
- 新增 `docs/why-not-just-git.md`：贴的是脚本真实输出，并写明这不是备份、多 GB 仓库不适用（f41e7f2）
- 干净 venv 里 `pip install git+https://...` 后脚本跑通，已验证（0fa667f）
- 补性能实测：415 MB tmpfs 478 ms、113 MB ext4 183 ms，写进文档当边界（f4f9dd5）
- 新增 `docs/claude-code-deleted-my-files.md`：按实际来源分流救援路径（/rewind 的官方限制、git 只救已提交、快照/回收站/编辑器历史），预防与事后分开写（59f499d、8004115）
- 仓库描述与 topics 改到"rollback / agent-safety / claude-code"，profile README 同步（703458b）
- 判断：同类项目十几个，最高 7 star。今天起不再加功能，只把"看懂 + 能验证"做到位
