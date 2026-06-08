#!/usr/bin/env python3
"""使用 OpenAI GPT Image 2 生成或编辑图片。

默认使用官方 OpenAI Image API：
- 文生图接口：/v1/images/generations
- 改图/参考图接口：/v1/images/edits

API Key：
- 优先读取 OPENAI_API_KEY 环境变量
- 也可以通过 --api-key 为单次调用传入
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


# 官方 OpenAI API 默认地址。仅在代理/网关完整兼容官方接口时覆盖。
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# 本 skill 专属模型：只允许 gpt-image-2 或它的官方 snapshot。
DEFAULT_MODEL = "gpt-image-2"

# 默认输出目录，保存图片和 last_image_generation_response.json。
DEFAULT_OUT_DIR = "tmp_files"

# --extra 不允许覆盖这些核心字段，避免高级参数破坏主流程。
PROTECTED_EXTRA_KEYS = {"model", "prompt", "image", "mask"}


def request_json(url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    """用 JSON body 调用 OpenAI 图片生成接口。

    Args:
        url: 完整请求地址。
        api_key: OpenAI API Key。
        payload: 要发送的 JSON 请求体。
        timeout: 超时时间，单位秒。

    Returns:
        解析后的 JSON 响应。
    """
    # JSON 请求体使用 UTF-8，保留中文提示词。
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    # urllib 标准库请求对象；避免脚本依赖第三方包。
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # errors="replace" 可以避免异常响应里混入非法字符时直接崩溃。
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text)
    except urllib.error.HTTPError as e:
        # OpenAI 通常会在响应头里带 x-request-id，排查问题时很有用。
        err = e.read().decode("utf-8", errors="replace")
        request_id = e.headers.get("x-request-id") if e.headers else None
        suffix = f" (request id: {request_id})" if request_id else ""
        raise RuntimeError(f"HTTP {e.code}{suffix}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Request failed: {e}") from e


def encode_multipart(fields: dict[str, Any], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    """把普通字段和文件字段编码为 multipart/form-data。

    Args:
        fields: 表单普通字段，例如 model、prompt、size。
        files: 文件字段列表，每项是字段名和本地文件路径。

    Returns:
        二进制请求体和 multipart boundary。
    """
    # 每次请求使用独立 boundary，避免和文件内容冲突。
    boundary = f"----gpt-image-2-{uuid.uuid4().hex}"

    # chunks 逐段收集二进制内容，最后一次性 join。
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                multipart_field_value(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for field_name, path in files:
        # 按文件名猜 MIME；猜不到时使用通用二进制类型。
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'.encode(),
                f"Content-Type: {mime}\r\n\r\n".encode(),
                path.read_bytes(),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def request_multipart(
    url: str,
    api_key: str,
    fields: dict[str, Any],
    files: list[tuple[str, Path]],
    timeout: int,
) -> dict[str, Any]:
    """用 multipart/form-data 调用图片编辑/参考图接口。

    Args:
        url: 完整请求地址。
        api_key: OpenAI API Key。
        fields: 表单普通字段。
        files: 表单文件字段，官方多参考图字段名为 image[]。
        timeout: 超时时间，单位秒。

    Returns:
        解析后的 JSON 响应。
    """
    body, boundary = encode_multipart(fields, files)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        request_id = e.headers.get("x-request-id") if e.headers else None
        suffix = f" (request id: {request_id})" if request_id else ""
        raise RuntimeError(f"HTTP {e.code}{suffix}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Request failed: {e}") from e


def multipart_field_value(value: Any) -> str:
    """把 Python 值转换成 multipart 表单字段里的字符串。

    bool 用 true/false；dict/list 用 JSON；其他值直接转字符串。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def unique_output_path(out_dir: Path, ext: str, index: int | None = None) -> Path:
    """生成不易冲突的输出文件路径。

    Args:
        out_dir: 输出目录。
        ext: 扩展名，例如 .png、.jpg、.webp。
        index: 多图结果中的序号；None 表示不追加序号。

    Returns:
        带时间戳和短 UUID 的图片路径。
    """
    ext = ext if ext.startswith(".") else f".{ext}"

    # 时间戳方便人看，短 UUID 防止同一秒多张图互相覆盖。
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    index_text = f"_{index + 1:02d}" if index is not None else ""
    return out_dir / f"generated_image_{timestamp}_{suffix}{index_text}{ext}"


def output_format_to_ext(output_format: str | None) -> str:
    """把 API 的 output_format 参数映射成本地文件扩展名。"""
    if output_format == "jpeg":
        return ".jpg"
    if output_format == "webp":
        return ".webp"
    return ".png"


def download_url(url: str, out_dir: Path, timeout: int, index: int | None = None) -> Path:
    """下载 URL 形式的图片结果并保存到本地。

    虽然 gpt-image-2 默认返回 b64_json，这里保留 URL 分支以兼容 API 返回形态变化。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "gpt-image-2-skill/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        content_type = resp.headers.get("content-type", "")
    ext = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ".png"
    out = unique_output_path(out_dir, ext, index)
    out.write_bytes(data)
    return out


def save_b64_image(
    b64_text: str,
    out_dir: Path,
    fallback_ext: str = ".png",
    index: int | None = None,
) -> Path:
    """保存 base64 图片数据到本地文件。

    Args:
        b64_text: 纯 base64 或 data URL。
        out_dir: 输出目录。
        fallback_ext: 无法从 data URL 判断类型时使用的扩展名。
        index: 多图结果中的序号。

    Returns:
        保存后的图片路径。
    """
    if b64_text.startswith("data:"):
        header, b64_text = b64_text.split(",", 1)
        mime = header.split(";", 1)[0].removeprefix("data:")
        ext = mimetypes.guess_extension(mime) or fallback_ext
    else:
        ext = fallback_ext
    out = unique_output_path(out_dir, ext, index)
    out.write_bytes(base64.b64decode(b64_text))
    return out


def save_result_images(result: dict[str, Any], out_dir: Path, fallback_ext: str) -> list[Path]:
    """从 OpenAI 响应中提取图片并保存。

    Args:
        result: OpenAI 返回的 JSON 响应。
        out_dir: 输出目录。
        fallback_ext: 默认扩展名。

    Returns:
        已保存的图片路径列表。没有可保存图片时返回空列表。
    """
    # Image API 的图片通常在 data 数组里，每个元素可能有 b64_json 或 url。
    data = result.get("data") or []
    paths: list[Path] = []
    if not isinstance(data, list):
        return paths

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        if "b64_json" in item:
            paths.append(save_b64_image(item["b64_json"], out_dir, fallback_ext, index))
        elif "url" in item:
            paths.append(download_url(item["url"], out_dir, 180, index))
    return paths


def file_uri_to_path(value: str) -> str:
    """把 file:// URI 转成本地路径；普通路径原样返回。

    Windows 路径常见形态是 file:///D:/path/to/file.png，需要额外去掉前导斜杠。
    """
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "file":
        return value
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        raise ValueError(f"Remote file URI is not supported: {value}")
    local_path = urllib.request.url2pathname(parsed.path)
    if os.name == "nt" and len(local_path) > 2 and local_path[0] in "\\/" and local_path[2] == ":":
        local_path = local_path[1:]
    return local_path


def normalize_image_paths(values: list[str]) -> list[Path]:
    """解析并校验 --image 参数。

    支持重复传参，也支持逗号分隔；每个路径必须存在且是文件。
    """
    paths: list[Path] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            part = file_uri_to_path(part)
            path = Path(part).expanduser()
            if not path.exists():
                raise FileNotFoundError(f"Reference image not found: {path}")
            if not path.is_file():
                raise ValueError(f"Reference image is not a file: {path}")
            paths.append(path)
    return paths


def normalize_optional_file(value: str | None, label: str) -> Path | None:
    """解析并校验可选文件参数，例如 --mask。"""
    if not value:
        return None
    path = Path(file_uri_to_path(value)).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is not a file: {path}")
    return path


def is_gpt_image_2_model(model: str) -> bool:
    """判断模型名是否属于 gpt-image-2 或官方 snapshot。"""
    return model == DEFAULT_MODEL or model.startswith(f"{DEFAULT_MODEL}-")


def parse_extra_params(values: list[str]) -> dict[str, Any]:
    """解析 --extra KEY=VALUE 高级参数。

    VALUE 会优先按 JSON 解析，因此 true、2、{"a":1} 这类值会保留类型。
    """
    params: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--extra must be KEY=VALUE, got: {value}")
        key, raw_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--extra key cannot be empty")
        if key in PROTECTED_EXTRA_KEYS:
            raise ValueError(f"--extra cannot override protected field: {key}")
        try:
            params[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            params[key] = raw_value
    return params


def add_image_options(payload: dict[str, Any], args: argparse.Namespace) -> None:
    """把用户显式传入的图片输出选项加入请求体。

    未传的选项保持缺省，让官方 API 使用自己的默认值。
    """
    if args.size:
        payload["size"] = args.size
    if args.quality:
        payload["quality"] = args.quality
    if args.output_format:
        payload["output_format"] = args.output_format
    if args.output_compression is not None:
        payload["output_compression"] = args.output_compression
    if args.background:
        payload["background"] = args.background
    if args.moderation:
        payload["moderation"] = args.moderation


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="使用 OpenAI gpt-image-2 生成或编辑图片。")
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"), help="OpenAI API Key。默认读取 OPENAI_API_KEY。")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="官方默认值：https://api.openai.com/v1。仅在 OpenAI API 网关/代理完整兼容时覆盖。")
    parser.add_argument("--mode", choices=["generate", "edit"], default="generate")
    parser.add_argument("--endpoint", default=None, help="覆盖接口路径。默认按模式使用 /images/generations 或 /images/edits。")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="只能使用 gpt-image-2 或官方 gpt-image-2 snapshot。")
    parser.add_argument("--prompt", required=True, help="图片提示词或编辑指令。")
    parser.add_argument("--image", action="append", default=[], help="参考图/输入图路径。可重复传入，也可用逗号分隔多张图。")
    parser.add_argument("--mask", default=None, help="可选编辑蒙版。蒙版作用于第一张输入图。")
    parser.add_argument("--n", type=int, default=1, help="生成图片张数。默认 1。")
    parser.add_argument("--size", default=None, help="不传则使用 API 默认 auto。例如：1024x1024、1536x1024、1024x1536、auto。")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default=None)
    parser.add_argument("--output-format", choices=["png", "jpeg", "webp"], default=None, help="输出格式。不传则使用 API 默认 png。")
    parser.add_argument("--output-compression", type=int, default=None, help="压缩比例 0-100，仅用于 jpeg/webp。")
    parser.add_argument("--background", choices=["auto", "opaque"], default=None, help="gpt-image-2 不支持透明背景。")
    parser.add_argument("--moderation", choices=["auto", "low"], default=None)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--extra", action="append", default=[], metavar="KEY=VALUE", help="高级官方 Image API 参数。可重复传入。")
    parser.add_argument("--dry-run", action="store_true", help="只打印最终请求，不调用 API。")
    return parser


def validate_args(args: argparse.Namespace) -> int:
    """校验命令行参数组合是否合法。

    Returns:
        0 表示通过；非 0 表示应作为进程退出码返回。
    """
    if not is_gpt_image_2_model(args.model):
        print("这个 skill 专用于 gpt-image-2。请使用 --model gpt-image-2 或官方 gpt-image-2 snapshot。", file=sys.stderr)
        return 2
    if args.n < 1:
        print("--n 必须大于或等于 1。", file=sys.stderr)
        return 2
    if args.output_compression is not None:
        if args.output_compression < 0 or args.output_compression > 100:
            print("--output-compression 必须在 0 到 100 之间。", file=sys.stderr)
            return 2
        if args.output_format not in {"jpeg", "webp"}:
            print("--output-compression 需要同时设置 --output-format jpeg 或 webp。", file=sys.stderr)
            return 2
    return 0


def main() -> int:
    """脚本入口：解析参数、构造请求、调用 API、保存结果。"""
    parser = build_parser()

    # args 保存所有命令行参数，是后续构造请求的主配置对象。
    args = parser.parse_args()

    # validation_status 为参数校验结果；非 0 时直接退出。
    validation_status = validate_args(args)
    if validation_status:
        return validation_status

    try:
        # image_paths 是所有参考图/输入图路径；mask_path 是可选局部编辑蒙版。
        image_paths = normalize_image_paths(args.image)
        mask_path = normalize_optional_file(args.mask, "Mask image")

        # extra_params 是用户通过 --extra 传入的高级官方参数。
        extra_params = parse_extra_params(args.extra)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2

    # 只要传了图片，就自动切到 edit 模式，减少用户漏写 --mode edit 的概率。
    mode = "edit" if image_paths and args.mode == "generate" else args.mode
    if mode == "edit" and not image_paths:
        print("edit 模式需要传入 --image /path/to/reference.png。", file=sys.stderr)
        return 2

    # endpoint 根据模式自动选择，也允许用户为调试兼容网关而覆盖。
    endpoint = args.endpoint or ("/images/edits" if mode == "edit" else "/images/generations")
    url = args.base_url.rstrip("/") + "/" + endpoint.lstrip("/")

    # payload 是最终发给 Image API 的核心请求体。
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": args.prompt,
        "n": args.n,
    }
    add_image_options(payload, args)
    payload.update(extra_params)

    # request_preview 用于打印请求摘要；文件只打印路径，不读取或输出文件内容。
    request_preview: dict[str, Any] = dict(payload)
    if mode == "edit":
        request_preview["image"] = [str(path) for path in image_paths]
        if mask_path:
            request_preview["mask"] = str(mask_path)

    if not args.dry_run and not args.api_key:
        print("缺少 API Key。请设置 OPENAI_API_KEY，或通过 --api-key 传入。", file=sys.stderr)
        return 2

    print(f"POST {url}")
    print(f"mode={mode}, model={args.model}, images={len(image_paths)}")
    print(json.dumps(request_preview, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("DRY RUN：未发送 API 请求。")
        return 0

    # out_dir 是所有图片和原始响应 JSON 的保存目录。
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if mode == "edit":
            # 官方 Image API 多参考图字段名为 image[]。
            files = [("image[]", path) for path in image_paths]
            if mask_path:
                files.append(("mask", mask_path))
            result = request_multipart(url, args.api_key, payload, files, args.timeout)
        else:
            result = request_json(url, args.api_key, payload, args.timeout)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    # 保存完整响应，方便排查用量、错误和返回结构变化。
    response_path = out_dir / "last_image_generation_response.json"
    response_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # fallback_ext 根据用户请求的输出格式决定；默认按 png 保存。
    fallback_ext = output_format_to_ext(args.output_format)
    outputs = save_result_images(result, out_dir, fallback_ext)
    if not outputs:
        print(f"没有找到图片数据。完整响应已保存到 {response_path}")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
        return 1

    for output in outputs:
        print(f"OK：图片已保存到 {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
