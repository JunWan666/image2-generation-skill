---
name: image2-generation-skill
description: 使用 OpenAI 官方 gpt-image-2 进行图片生成、改图、局部编辑、参考图生成和多参考图合成。触发词包括 images2、image2、图片2、画图2、生成图2、改图2、编辑图2、参考图2、垫图2、按图2，以及用户明确要求用 gpt-image-2、OpenAI Image API、/v1/images/generations 或 /v1/images/edits 生成/编辑图片。默认使用官方 OpenAI API，仅在代理或网关完整兼容 OpenAI 官方 gpt-image-2 Image API 时才覆盖 base URL。
---

# GPT Image 2 图片生成 / 编辑

这个 skill 专门用于 OpenAI 官方 `gpt-image-2` 图片工作流：文生图、改图、局部编辑、参考图生成、多参考图合成。默认走官方 OpenAI Image API，不默认绑定任何第三方服务。

## 默认设置

- Base URL: `https://api.openai.com/v1`
- 文生图接口: `/images/generations`
- 改图/参考图接口: `/images/edits`
- 模型: `gpt-image-2`
- Key: 优先读 `OPENAI_API_KEY`
- 输出目录: 默认当前工作目录下的 `tmp_files`

## 触发方式

把这些词当成明确要使用本 skill：

- 文生图: `images2`, `image2`, `图片2`, `画图2`, `生成图2`
- 改图/参考图: `改图2`, `编辑图2`, `参考图2`, `垫图2`, `按图2`
- API/模型关键词: `gpt-image-2`, `OpenAI Image API`, `/v1/images/generations`, `/v1/images/edits`

如果用户只发触发词，没有提示词，就询问要生成什么图。  
如果用户要求改图、参考图或垫图，但没有图片路径/附件，就请用户提供参考图。

## 工作流

1. 判断模式：
   - 没有输入图或参考图：使用 `generate`。
   - 有输入图、参考图，或用户要求编辑/重绘/改风格：使用 `edit`。
2. 把用户需求整理成清晰中文提示词，必要时补充构图、主体、风格、色彩、比例、文字要求和禁止项。
   - 需要选择 1K/2K/4K、1:1、16:9、9:16 等尺寸时，读取 `references/gpt-image-2.md`。
3. 执行 `scripts/generate_image.py`。
4. 把生成图片路径返回给用户；如果当前环境有消息/附件工具，再按用户期望发送图片。

## 文生图

```bash
python scripts/generate_image.py \
  --prompt "一只穿着宇航服的橘猫站在月球上，电影感光照，高细节" \
  --out-dir "tmp_files"
```

如果没有设置环境变量，也可以单次传 key：

```bash
python scripts/generate_image.py \
  --api-key "sk-..." \
  --prompt "月光蓝色调的 AI 助手头像，干净背景，柔和边缘光"
```

## 改图 / 参考图

单张参考图：

```bash
python scripts/generate_image.py \
  --mode edit \
  --image "/absolute/path/to/reference.png" \
  --prompt "保留人物五官和发型，改成国风茶饮联动商业海报，柔和暖光"
```

多张参考图：

```bash
python scripts/generate_image.py \
  --mode edit \
  --image "/path/person.png" \
  --image "/path/brand-style.png" \
  --prompt "参考第一张的人物，参考第二张的配色和包装氛围，生成一张茶饮联动海报"
```

局部编辑：

```bash
python scripts/generate_image.py \
  --mode edit \
  --image "/path/source.png" \
  --mask "/path/mask.png" \
  --prompt "只替换蒙版区域，把泳池里加入一只粉色火烈鸟，其余环境保持一致"
```

`gpt-image-2` 的 mask 会作为提示引导，不保证逐像素严格贴合。mask 应与第一张输入图尺寸一致，并带 alpha 通道。

## 常用参数

- `--prompt`: 图片提示词，必填。
- `--mode generate|edit`: 生成或编辑；如果传了 `--image`，脚本会自动转为 `edit`。
- `--image /path/to/img.png`: 输入图/参考图；可重复，也可逗号分隔。
- `--mask /path/to/mask.png`: 局部编辑蒙版，作用于第一张输入图。
- `--n 1`: 生成张数。
- `--size`: 输出尺寸；不传则使用 API 默认 `auto`。常用 1K/2K/4K 和比例速查见 `references/gpt-image-2.md`。
- `--quality low|medium|high|auto`: 质量；草稿优先 `low`，最终图优先 `medium` 或 `high`。
- `--output-format png|jpeg|webp`: 输出格式；不传则 API 默认 `png`。
- `--output-compression 0-100`: 只用于 `jpeg`/`webp`。
- `--background auto|opaque`: `gpt-image-2` 不支持透明背景，不要传 `transparent`。
- `--moderation auto|low`: 内容审核强度。
- `--out-dir`: 保存图片和原始响应 JSON 的目录。
- `--dry-run`: 打印最终请求，不真正调用 API。

## 高级自定义边界

这个 skill 是 `gpt-image-2` 专属，不要把它当成任意图片模型路由器。  
允许的自定义主要用于官方参数、代理和排错：

- `--model`: 只使用 `gpt-image-2` 或官方 `gpt-image-2-*` snapshot。
- `--base-url`: 默认不要设置。只有在企业代理、API 网关或中转服务完整保持 OpenAI 官方 Image API 语义时才覆盖。
- `--endpoint`: 仅在调试官方兼容路径时覆盖。
- `--extra KEY=VALUE`: 传入脚本尚未显式支持的简单官方 Image API 参数。值会先尝试按 JSON 解析，例如 `--extra some_flag=true` 或 `--extra some_number=2`。不要用它开启流式返回；当前脚本按普通 JSON 响应保存图片。

不要用 `--extra` 覆盖 `model`、`prompt`、`image`、`mask`，脚本会拒绝这些字段。

## 结果

脚本会打印：

```text
OK: saved image to /absolute/path/generated_image_YYYYMMDD_HHMMSS_xxxxxxxx_01.png
```

同时保存原始响应：

```text
<out-dir>/last_image_generation_response.json
```

如果请求被内容审核拦截、配额不足、参数无效或网络失败，优先查看终端错误和 `last_image_generation_response.json`。对 `moderation_blocked` 一类错误，修改提示词或参考图后再重试；不要盲目重复同一个请求。
