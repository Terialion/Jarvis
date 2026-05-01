# Hardcode Cleanup Report — LLM-First Semantic Routing Refactor

## Summary

This cleanup removes natural language hardcoded rules from the deterministic
router and natural_responses renderer, migrating them to the LLM semantic
classifier which is now the primary natural language routing path.

## Deleted Rules (from deterministic_router.py)

| Rule | Previous Behavior | Now Handled By |
|------|------------------|----------------|
| `_SKILL_QUERY_ZH` (7 items: 有哪些技能, 我能用哪些技能, etc.) | Exact match → skill_management | LLM IntentClassifier |
| `_SKILL_QUERY_EN` (4 items: list skills, show skills, etc.) | Exact match → skill_management | LLM IntentClassifier |
| `_CHAT_JOKE_ZH` (5 items: 给我讲个笑话, 讲个冷笑话, etc.) | Exact match → chat_answer | LLM IntentClassifier |
| `_CHAT_JOKE_EN` (3 items: tell me a joke, cheer me up, etc.) | Exact match → chat_answer | LLM IntentClassifier |
| `_WORKSPACE_STATUS_ZH` (4 items: 我现在的目录是什么, etc.) | Exact match → workspace_status | LLM IntentClassifier |
| `_WORKSPACE_STATUS_EN` (3 items: what directory am i in, etc.) | Exact match → workspace_status | LLM IntentClassifier |
| Repo inspection tokens: 帮我检查一下这个项目的结构, 检查一下项目, 检查项目结构 | Substring match → repo_inspection | LLM IntentClassifier |
| Search token hack: 查一下 → 查一下  (trailing space) | Avoided matching 检查一下 | Removed — no longer needed |
| Duplicate `_looks_like_repo_inspection` call | Second check after search rules | Removed duplicate |

## Deleted Logic (from natural_responses.py)

| Logic | Previous Behavior | Replacement |
|-------|------------------|-------------|
| `if "笑话" in user_input` | Parsed user input for joke intent | `render_chat_answer` now uses `route["response_mode"] == "joke_answer"` |
| `joe_tokens_zh` set check | Hardcoded set of joke phrases | Removed — intent determined by router |
| `random.choice(jokes)` in input-matching branch | Joke rendering tied to input text | Moved to `if mode == "joke_answer"` branch |
| `render_chat_answer(user_input)` signature | Only took user_input | Now `render_chat_answer(route, user_input)` — route-first |
| `render_workspace_status(user_input, workspace_root)` | Took raw user_input | Now `render_workspace_status(route, workspace_root)` — route-first |

## Kept Rules (deterministic_router.py)

| Rule | Reason |
|------|--------|
| Empty input | Structural — always clarify |
| Slash commands | Command routing — pre-processed |
| Greetings (hello, 你好, etc.) | Extremely short, exact-match, universal |
| Identity (你是谁, who are you) | Exact-match, always the same answer |
| Capability (你能做什么, what can you do) | Exact-match, help page |
| Usage help (怎么让你改代码) | Exact-match, help page |
| Context resume (继续上次任务) | Exact-match, admin action |
| Skill management tokens (查看skill, 列出 skills) | Direct management action with explicit tokens |
| Automation requests | Exact-match, unsupported feature |
| URL detection | Structural — has_url envelope |
| Web search hints | Structural — 搜一下, search, etc. |
| Repo inspection structural tokens | Read-only patterns (读项目, 看看这个仓库) |
| Coding creation (写 + code_object) | Creation pattern requires write + approval |
| Coding modification (修复, 改一下) | Modification pattern requires write + approval |
| Shell execution (运行 pytest, git status) | Explicit shell commands |
| Non-code writing ambiguity (写个东西) | Genuinely ambiguous — needs clarification |
| Generic ambiguity (弄一下, 随便) | Genuinely ambiguous — needs clarification |

## Kept Rules (intent_gateway.py)

| Rule | Reason |
|------|--------|
| Safety precheck (.env, .ssh, id_rsa) | Non-negotiable safety |
| Destructive request (rm -rf, 删除整个项目) | Non-negotiable safety |
| Dangerous shell (curl | sh, etc.) | Non-negotiable safety |

## Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| test_llm_semantic_router.py | 21 | All pass |
| test_clarification_policy_not_overeager.py | 22 | All pass |
| test_no_natural_response_intent_matching.py | 9 | All pass |
| test_llm_semantic_routing_ab.py | 3 | All pass |
| test_intent_gateway.py | 6 | All pass |
| test_llm_fallback_classifier.py | 2 | All pass |
| test_clarification_policy.py | 2 | All pass |
| test_prompt_builder.py | 2 | All pass |
| smoke_cli_natural_ux.py | 20 cases | All pass |
| inspect_intent_route.py | 55 cases | All pass |
| **Total** | **142** | **All pass** |

## Verification Commands

```bash
python -m pytest tests/routing/ tests/llm/ tests/security/ -q     # 63 passed
python -m pytest tests/cli/ -q                                     # 147 passed
python scripts/inspect_intent_route.py                              # 55/55 passed
python scripts/smoke_cli_natural_ux.py                             # All passed
```
