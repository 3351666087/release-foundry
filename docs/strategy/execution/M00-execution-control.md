# M00 Execution Control

## Checklist

- [x] `M00-01` 确认唯一总战略路径。
- [x] `M00-02` 建立模块索引和稳定任务 ID。
- [x] `M00-03` 定义最小上下文加载规则。
- [x] `M00-04` 定义“证据先于勾选”的完成规则。
- [x] `M00-05` 把模块索引路径写入持久 `/goal`。
- [x] `M00-06` 规定每轮只推进一个主条目并更新 Evidence Log。

## Definition Of Done

任意新 Agent 窗口只读取模块索引和 Current Pointer，即可知道当前任务、边界、未完成项和验证方式。

## Evidence Log

- `2026-07-20`: modular index created at `docs/strategy/execution/README.md` from main baseline `c32d635ecb100a585369188f86f5c184c8645775`.
