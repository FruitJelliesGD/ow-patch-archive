---
feature: ai-translate-tool
status: delivered
updated: 2026-10-23
---

# 缺失中文补丁的批量 AI 翻译工具

## Report

**What was built** — 新增 `src/ow2_patch/ai_translate.py` + `tools/ai_translate.py`，从 `patches_index.json` 找出所有 `patch_id_cn` 为空的 EN 补丁，按技能提示词与 v7.6 术语表分批翻译，拼装为 `data/ai_translations/zh/<year>/<date>-<seq>.json` 并重建 `index.json`。默认直接复用 `owpatch-tool` WebUI 保存的 `ui-config.toml` 凭据（`OWPATCH_API_KEY` 可覆盖），因此本地无需另配 key。

**Verification** —
- 7 篇试跑（2018 PTR / 2019 / 2020 / 2023 最大补丁 / 2025 stadium / 2026 最新 / 2026 公告）全部通过结构、数字与中文校验。
- 随后全量回填 288 篇（含试跑与原有 3 篇），`validate` 0 错误。
- `pytest -q` → **323 passed**；`node tools/_smoke_web.js` → ALL WEB ASSERTIONS OK。
- 站点新增 `ai-translate.yml`；`pages.yml` 在 AI 提交后自动重建。

## [S1] Problem

官方中文站 2016-2025 历史缺失，`patches_index` 中 288 篇只有英文；手工逐篇翻译不可维护，且直接把机器译文写进 `data/patches/cn` 会污染官方配对、英雄时间线与词条检索。

## [S2] Design

### D1 数据流

```
patches_index.json (no patch_id_cn)
  -> source EN JSON
  -> flatten units (section/hero/perk/ability/stadium/block/map)
  -> batches (6000 chars)
  -> OpenAI-compatible chat (skill prompt + filtered terms)
  -> build AI JSON (text_cn, text_en=null, names, metadata)
  -> validate (structure/numbers/bullets/Chinese)
  -> data/ai_translations/zh/YYYY/<date>-<seq>.json
  -> rebuild index.json
```

### D2 凭据优先级

`OWPATCH_API_KEY` > `--translate-config` > `<OWPATCH_DATA_DIR>/ui-config.toml`（默认 `%LOCALAPPDATA%\owpatch-tool\ui-config.toml`） > `../owpatch-tool/config.toml`。
Key 只在内存中使用，`status --json` 只输出 `api_key_set` 与来源；日志不打印 key。

### D3 提示词

- 读取 `data/ai_translations/skill/system_prompt.md`（技能 v7.6 的运行时提示词副本）。
- 取 `## 输出契约` 之前的规则，追加 JSON 模式契约：输入 `[{id,kind,context,text}]`，输出 `{id: 中文}`。
- 每批按文本命中注入术语 + `core_terms`，避免整表重复发送。
- `title` 程序化生成，不让模型翻译。

### D4 校验

硬校验：结构/数量/顺序、`text_en=null`、`text_cn` 中文非空、`slug/name_en/role/icon` 不变、changes 的数字提取字段不变、列表符号/缩进一致、无占位符/整句英文。
数字 token 仅对带 `before/after/by/by_pct` 的统计行硬校验；普通说明文字允许「Mouse 1→鼠标左键」这类自然改写。

### D5 运行

```bash
python tools/ai_translate.py status
python tools/ai_translate.py run --missing --order oldest --concurrency 3 --model deepseek-chat
python tools/ai_translate.py validate
python tools/ai_translate.py index
```

断点续跑：已有文件且 `translation.source_hash` 与源一致则跳过；`--force` 重译。每篇独立失败，不阻塞其他篇；失败时退出非零并列出清单。

### D6 未来自动化

`ai-translate.yml` 在 monitor/monitor-fast/watchdog 成功后运行，默认只翻译最近 14 天、最多 10 篇；需要仓库 Secret `OWPATCH_API_KEY`，否则打印说明并跳过。`pages.yml` 增加 `ai-translate` 触发，AI 提交后自动重建站点。

## Journey log

① CI 首次运行全部 `FileNotFoundError: .../python3.12/data/patches_index.json`：`pip install .` 后包的 `__file__` 位于 site-packages，`parents[2]/data` 不再是仓库根目录。修复为 `main()` 默认优先使用 `Path.cwd()/data`，并在 workflow 的仓库根目录执行；已用安装布局模拟验证 `status` / `run` 均正常。

## 已知边界

- 全量历史回填手动运行；定时任务只补最近补丁，避免一次性费用。
- 官方中文后来补上时，`run` 不再选择该补丁，已有 AI 文件保留（站点仍可看 AI 翻译）。
- `deepseek-flash` 在本机响应较慢/易 SSL 断连，实际全量使用 `--model deepseek-chat`；模型可通过 `--model`/`OWPATCH_API_MODEL` 覆盖。
- 数字校验对普通 prose 放宽，统计行仍硬校验。
