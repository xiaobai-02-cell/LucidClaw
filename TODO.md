# TODO

## 代码问题

- [ ] **`save_user_profile` docstring 引用了不存在的 `read_user_profile` 工具** (`lucidclaw/core/tools/builtins.py:39`)
  - docstring 要求："请先调用 read_user_profile 获取当前的完整档案"，但 `BUILTIN_TOOLS` 中并没有这个工具
  - 当前实际流程：画像内容由 `agent.py` 每轮通过系统 Prompt 注入，LLM 在上下文中直接看到
  - 风险：LLM 严格遵循 docstring 指引时可能尝试调用不存在的工具而报错
  - 修复方向：要么补上 `read_user_profile` 工具，要么删除 docstring 中那句指引
