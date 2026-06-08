<div align="center">
  <h1>image2-generation-skill</h1>
  <p>面向 OpenAI <code>gpt-image-2</code> 的中文图片生成 / 编辑 Agent Skill。</p>
  <p>
    <img alt="Skill" src="https://img.shields.io/badge/Agent-Skill-111827?style=flat-square">
    <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white">
    <img alt="OpenAI" src="https://img.shields.io/badge/OpenAI-gpt--image--2-10a37f?style=flat-square&logo=openai&logoColor=white">
    <img alt="Language" src="https://img.shields.io/badge/Language-中文为主-dc2626?style=flat-square">
  </p>
  <p>
    <a href="#项目简介">项目简介</a> ·
    <a href="#适用范围">适用范围</a> ·
    <a href="#功能特性">功能特性</a> ·
    <a href="#快速开始">快速开始</a> ·
    <a href="#常用参数">常用参数</a> ·
    <a href="#目录结构">目录结构</a> ·
    <a href="#安全说明">安全说明</a>
  </p>
</div>

## 项目简介

`image2-generation-skill` 是一个面向中文工作流的通用 Agent Skill，专门用于通过 OpenAI 官方 `gpt-image-2` 进行图片生成、图片编辑、局部编辑和参考图生成。

项目默认使用官方 OpenAI Image API，不默认绑定第三方服务；仅在代理或网关完整兼容 OpenAI 官方 `gpt-image-2` Image API 时，才建议覆盖 `--base-url`。

## 适用范围

本仓库不是某一个 Agent 的专属扩展。它采用常见的 `SKILL.md + scripts/` 结构，只要目标 Agent 运行时支持读取 `SKILL.md`，并允许执行本地 Python 脚本，就可以按各自的安装规则使用。

可作为以下类型工具的技能包基础：

- Codex / OpenAI 风格 skills
- Claude Code skills
- OpenClaw skills
- Hermes 或其他支持 `SKILL.md` 工作流的 Agent

不同 Agent 的技能目录、权限确认、环境变量读取方式可能不同；核心能力由 `SKILL.md` 和 `scripts/generate_image.py` 提供。

## 功能特性

- 文生图：调用 `/v1/images/generations`。
- 改图/参考图：调用 `/v1/images/edits`。
- 支持单张或多张参考图。
- 支持局部编辑蒙版。
- 支持尺寸、质量、输出格式、压缩比例、背景、审核强度等官方参数。
- 默认读取 `OPENAI_API_KEY`，也支持通过 `--api-key` 单次传入。
- 脚本注释、命令行说明和 skill 文档以中文为主。
- 支持 `--dry-run` 预览最终请求，不实际调用 API。

## 快速开始

先设置 API Key：

```powershell
$env:OPENAI_API_KEY="sk-..."
```

文生图：

```powershell
python scripts\generate_image.py `
  --prompt "一只穿着宇航服的橘猫站在月球上，电影感光照，高细节"
```

参考图生成或改图：

```powershell
python scripts\generate_image.py `
  --mode edit `
  --image "D:\path\reference.png" `
  --prompt "保留人物五官和发型，改成国风茶饮联动商业海报，柔和暖光"
```

局部编辑：

```powershell
python scripts\generate_image.py `
  --mode edit `
  --image "D:\path\source.png" `
  --mask "D:\path\mask.png" `
  --prompt "只替换蒙版区域，把背景改成夜晚霓虹街道，其余主体保持一致"
```

只检查请求，不调用 API：

```powershell
python scripts\generate_image.py `
  --prompt "测试图片" `
  --quality high `
  --size 1024x1024 `
  --dry-run
```

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--prompt` | 图片提示词或编辑指令，必填 |
| `--mode generate\|edit` | 生成或编辑；传入 `--image` 时会自动切到 `edit` |
| `--image` | 参考图或输入图路径，可重复传入，也可逗号分隔 |
| `--mask` | 局部编辑蒙版，作用于第一张输入图 |
| `--n` | 生成图片张数，默认 `1` |
| `--size` | 输出尺寸，例如 `1024x1024`、`1536x1024`、`1024x1536` |
| `--quality` | `low`、`medium`、`high`、`auto` |
| `--output-format` | `png`、`jpeg`、`webp` |
| `--output-compression` | JPEG/WebP 压缩比例，范围 `0-100` |
| `--background` | `auto` 或 `opaque`，`gpt-image-2` 不支持透明背景 |
| `--moderation` | 内容审核强度，`auto` 或 `low` |
| `--out-dir` | 输出目录，默认 `tmp_files` |
| `--dry-run` | 打印最终请求，不调用 API |

## 目录结构

```text
image2-generation-skill/
├─ SKILL.md
├─ README.md
├─ .gitignore
└─ scripts/
   └─ generate_image.py
```

## 默认接口

默认 API 地址：

```text
https://api.openai.com/v1
```

默认模型：

```text
gpt-image-2
```

默认接口：

```text
/images/generations
/images/edits
```

## 安全说明

- 不提交真实 API Key、截图中的 Key 或示例 Key。
- 不把 Key 写进 `SKILL.md`、`README.md` 或脚本默认值。
- 优先使用 `OPENAI_API_KEY` 环境变量。
- 生成图片、响应 JSON 和临时目录默认不进入版本控制。
