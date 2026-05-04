# 04. Claude Code 参考重点

Claude Code 公开包里最有参考价值的是 **hooks、permissions、skills、命令 frontmatter**，它们适合拿来补 Jarvis 的工具治理层。

## 关键参考点

1. `settings-strict.json` 展示了安全策略如何分层：禁 bypass、Bash ask、WebSearch/WebFetch deny、sandbox 网络限制。
2. `bash_command_validator_example.py` 展示 PreToolUse hook 如何在工具执行前拦截/提示。
3. `hook-development/SKILL.md` 把 Hook 类型分成 PreToolUse、PostToolUse、Stop、SessionStart、PreCompact 等。
4. `skill-development/SKILL.md` 展示 skill 的结构：`SKILL.md` + scripts + references + assets。
5. `commit.md` frontmatter 的 `allowed-tools` 是 Jarvis 命令/skill 权限声明的好模板。

## Jarvis 可借鉴的结构

```text
ToolCall
  -> policy check
  -> PreToolUse hooks
  -> approval if needed
  -> execute
  -> PostToolUse hooks
  -> normalized ToolResult
```

对应到 Jarvis：

```text
ToolExecutor.execute()
  -> ApprovalRiskMatrix.classify(call)
  -> HookExecutor.run('before_tool_call')
  -> delegate to existing tool/skill
  -> HookExecutor.run('after_tool_call')
```