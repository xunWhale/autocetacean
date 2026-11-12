# AutoCetacean 项目进度

- 给谁用：AutoCetacean 确定性状态机 Agent 框架开发者。
- 解决什么：从 JSON/JSONL 或运行时上下文回放执行步骤，展示状态迁移、自愈重试、检查点回滚，并导出 HTML 与统计摘要。
- 已完成：`ReplayEngine`、`autocetacean replay` CLI、单元测试、README 使用示例；schema 校验失败现在会记录结构化 violation，并由 graph trace 与 replay terminal/HTML/summary 展示。
- 下一步：如需集成真实运行时日志，可在记录步骤时补充 `state_before/state_after/status/checkpoint_id` 元数据。
- 踩过的坑：现有 `ExecutionContext.trajectory` 的 `StepRecord` 不含显式状态快照，因此 replay 会优先读取 metadata 中的快照，缺失时兼容使用 input/output 数据。
