# AI翻译（实验性，非官方）

这里是归档仓库的 **AI 机器翻译** 目录，与官方英文/中文数据完全隔离。当前覆盖全部 **288 篇**缺少官方中文的补丁（2016-2026，含公告/PTR/愚人节等特殊模式）。

- 官方数据：`data/patches/en`、`data/patches/cn`、`data/archive/en`、`data/archive/cn`
- 本目录：`data/ai_translations/`（不进入 `patches_index.json`、`entries_index.json`、英雄时间线、词条检索）

## 免责声明

- 译文由 OpenAI 兼容接口（DeepSeek）按 `overwatch-patch-translation` 技能 v7.6 生成；实际模型记录在每个文件的 `translation.model`。
- **不是官方中文**；内容、数值、语气均可能与官方原文有出入。以 `source_patch_id` 指向的英文原文为准。
- 文件里的 `translation.status` 为 `draft`，表示尚未人工复核。

## 目录结构

```text
data/ai_translations/
├── README.md
├── index.json
└── zh/2016/
    ├── 2016-06-14-1.json
    ├── 2016-09-02-1.json
    └── 2016-12-13-1.json
```

## `index.json`

```json
{
  "schema_version": 1,
  "updated": "2026-10-23T00:00:00Z",
  "notice": "AI 机器翻译，非官方中文；内容与数值以英文原文为准。",
  "translations": [
    {
      "source_patch_id": "en-2016-06-14-1",
      "ai_patch_id": "ai-2016-06-14-1",
      "date": "2016-06-14",
      "title": "《守望先锋》补丁说明——2016年6月14日",
      "file": "zh/2016/2016-06-14-1.json",
      "status": "draft"
    }
  ]
}
```

- 站点以 `source_patch_id` 匹配 `patches_index.json` 里的补丁（兼容 `p-…` 合并条目的 `patch_id_en`）。
- `file` 相对 `data/ai_translations/`。

## 补丁 JSON

结构镜像 `data/patches/*.json`，但使用独立命名空间：

- `id`: `ai-<date>-<seq>`（例 `ai-2016-06-14-1`）
- `site`: `"ai"`
- `hash`: `null`（不参与官方内容哈希）
- `source_patch_id` / `translation.source_hash`: 源补丁与源内容哈希
- `text_en`: 全部为 `null`；`text_cn` 为中文译文
- `before/after/by/by_pct/metric/raw_metric/unit`、`slug`、`name_en`、`role`、`icon`：与源文件一致，**不要改**

## 在站点查看

本地：

```bash
python tools/serve.py
# http://127.0.0.1:8000/patch.html?id=en-2016-06-14-1&lang=ai
```

线上：`pages.yml` 会把 `data/ai_translations/` 一并部署到 `_site/data/`，push 后生效。补丁页会出现「AI翻译」标签，列表页对应条目显示「AI翻译」徽章。

## 批量补齐

```bash
python tools/ai_translate.py status
python tools/ai_translate.py run --missing --order oldest --concurrency 3 --model deepseek-chat
python tools/ai_translate.py validate
```

凭据优先级：`OWPATCH_API_KEY` > `--translate-config` > `<owpatch-tool data>/ui-config.toml` > `../owpatch-tool/config.toml`。
本地会直接复用 owpatch-tool WebUI 保存的 key；GitHub Actions 使用仓库 Secret `OWPATCH_API_KEY`。

## 新增一篇

1. 手动翻译：复制对应英文源 JSON 的结构，翻译 `title` / section 标题与说明 / 开发者注 / `general` / `text_cn` / block 标题与正文；保留全部数字、列表层级、`slug`/`name_en`。
2. 标题日期取源 JSON 的 `date`（与归档/列表一致），格式 `《守望先锋》补丁说明——YYYY年M月D日`。
3. 在 `index.json` 增加条目，`status` 先写 `draft`。
4. 跑 `pytest -q tests/test_ai_translations.py` 校验结构、数字与中文覆盖。
5. 不要修改 `data/patches/{en,cn}` 或官方索引；不要运行 `tools/rebuild.py` 期待 AI 数据被索引。
