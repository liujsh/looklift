# v0.5 供应商与批量分析实施计划

> **执行说明:** 按 AGENTS.md 的 TDD 分场景规则由单智能体线性执行；provider 协议、错误映射、配置解析、batch 断点与互斥行为 test-first，GUI 粘合 code-first 后补特征测试。每个任务形成一个可测完整提交，成型代码边界统一自审。

**Goal:** 接入标准 OpenAI Chat Completions vision 与 Ollama vision，扩展 GUI 配置，并交付可断点续跑的目录批量分析。

**Architecture:** `providers.py` 保留 provider 协议、wire 翻译与工厂；新建 `provider_http.py` 统一标准库 JSON POST、超时和一次重试；新建 `batch.py` 负责目录扫描、原子结果与续跑，CLI/GUI 只做入口。模型输出仍由 analyzer 统一 `_normalize`。

**Tech Stack:** Python 3.11+、stdlib urllib/json、Pillow、现有 pywebview 前端；测试全部离线。

## 全局约束

- 不改变 Anthropic API 与 Claude CLI 行为。
- `provider` 扩展为 `auto|cli|api|openai_compat|ollama`；timeout 留空时按 provider 默认。
- OpenAI 图片使用完整 data URI；Ollama images 使用纯 base64。
- 连接错误/5xx 重试一次；4xx 不重试；最终错误必须中文且含修复建议。
- batch 结果只写组内 `.looklift-result.json`，不自动进入风格库。
- 不实现聚类；版本完成时推进到 0.5.0。

---

## Task 1: 配置与 provider 工厂

**Files:** `looklift/config.py`、`looklift/providers.py`、`looklift/analyzer.py`、`tests/test_config.py`、`tests/test_providers.py`

**Produces:** timeout 配置/env 覆盖；新 provider 名称解析；`resolve_backend()` 返回真实 provider 名。

- [ ] test-first:覆盖 timeout 默认/文件/env、非法 timeout 中文错误、显式/auto provider 选择。
- [ ] 实现配置解析与 factory 骨架，不实现网络调用。
- [ ] 跑 config/providers focused tests；通过后提交。

## Task 2: 公共 HTTP 层与 OpenAICompatProvider

**Files:** 新建 `looklift/provider_http.py`；修改 `looklift/providers.py`；修改 `tests/test_providers.py`

**Produces:** JSON POST、一次重试、OpenAI vision wire 翻译与中文错误。

- [ ] test-first:正常响应、data URI、timeout、401/404、连接失败、5xx 重试一次、模型文本 JSON 提取。
- [ ] 实现标准库 transport 与 OpenAICompatProvider；opener/sleeper 可替换以离线测试。
- [ ] 跑 provider focused tests；确认旧 provider 不回归后提交。

## Task 3: OllamaProvider

**Files:** `looklift/providers.py`、`tests/test_providers.py`

**Produces:** `/api/chat` wire 翻译、纯 base64 images、服务/模型错误中文化。

- [ ] test-first:正常响应、默认地址、图片无 data URI 前缀、服务未启动、模型未 pull。
- [ ] 实现 OllamaProvider 并复用 transport/JSON 提取。
- [ ] 跑 provider/analyzer focused tests；通过后提交。

## Task 4: 可续跑 batch 核心与 CLI

**Files:** 新建 `looklift/batch.py`、`tests/test_batch.py`；修改 `looklift/cli.py`、`tests/test_cli.py`

**Produces:** 组扫描、最多 5 图、原子 `.looklift-result.json`、续跑/force、失败汇总与退出码。

- [ ] test-first:三组首次运行、已有结果跳过、force 重算、单组失败继续、图片排序/截断、空目录、参数互斥。
- [ ] 实现 batch 核心；CLI `edited` 改为可空并在解析后强制单次/batch 二选一。
- [ ] 输出开始额度提示、逐组进度与失败汇总；跑 batch/CLI tests 后提交。

## Task 5: GUI provider 配置

**Files:** `looklift/gui/api.py`、`looklift/gui/static/index.html`、`looklift/gui/static/js/app.js`、相关 GUI tests

**Produces:** 新 provider 选项；base_url/model/timeout 联动；Ollama 隐藏 key；配置 API 不泄露 key。

- [ ] code-first 完成表单/API 粘合，保持首次向导复用同一表单结构。
- [ ] 补特征测试:允许新 provider、timeout 落盘、GET 回显非敏感字段、Ollama key 区隐藏。
- [ ] 跑 GUI config/server tests；浏览器静态行为人工验收后提交。

## Task 6: 文档、版本与最终验收

**Files:** `README.md`、`docs/design.md`、`pyproject.toml`、必要测试

**Produces:** 配置示例、batch 用法、实现实况、版本 0.5.0。

- [ ] README 写 OpenAI-compatible/Ollama 配置和 batch 目录约定；design 回填已实现架构。
- [ ] 版本改为 0.5.0；先运行 provider/batch/GUI 相关测试，全量套件留到本任务最后收口。
- [ ] 成型代码自审：离线、中文错误、无密钥泄露、旧 provider 不回归、单文件职责。
- [ ] 提交收尾；真实中转站/Ollama/batch 留给人工验收清单。

## 完成条件

spec 与计划契约无矛盾即冻结；实现完成后仅在 Task 6 收口运行一次 `pytest -q`，真实 OpenAI-compatible、Ollama 与照片目录各人工跑通一次。
