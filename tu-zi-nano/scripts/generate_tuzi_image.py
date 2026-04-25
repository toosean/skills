#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request


DEFAULT_BASE_URL = "https://api.tu-zi.com"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1:1"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 360.0
DEFAULT_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "logs" / "generation-history.jsonl"
)

IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
DOWNLOAD_MARKDOWN_RE = re.compile(
    r"\[[^\]]*(?:点击下载|下载|download)[^\]]*\]\((https?://[^)\s]+)\)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s)\]>]+")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate an image with the Tu-Zi chat completions API.",
    )
    parser.add_argument("--prompt", required=True, help="Image prompt.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name.")
    parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help="Desired output ratio. Non-default values are folded into the prompt.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature passed to the API.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Request and download timeout in seconds.",
    )
    parser.add_argument(
        "--reference-image-path",
        action="append",
        help="Absolute path to a local reference image. Repeat to pass multiple images in order.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory where the generated image will be saved. Defaults to a temp folder.",
    )
    parser.add_argument(
        "--file-name",
        help="Optional output file name. Extension is inferred when possible.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Return the image URL without downloading the file.",
    )
    parser.add_argument(
        "--log-file",
        help=(
            "Optional path for the JSONL generation log. Defaults to "
            "the skill's logs/generation-history.jsonl."
        ),
    )
    return parser


def require_api_key():
    api_key = os.environ.get("TU_ZI_API_KEY")
    if api_key:
        return api_key
    raise RuntimeError("Missing TU_ZI_API_KEY environment variable.")


def configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def write_stdout(message):
    text = f"{message}\n"
    try:
        sys.stdout.buffer.write(text.encode("utf-8", errors="backslashreplace"))
    except Exception:
        print(text, end="")


def write_stderr(message):
    text = f"{message}\n"
    try:
        sys.stderr.buffer.write(
            text.encode("utf-8", errors="backslashreplace")
        )
    except Exception:
        print(text, file=sys.stderr, end="")


def decode_body(body, headers):
    charset = headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def resolve_log_path(raw_path=None):
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return DEFAULT_LOG_PATH


def append_generation_log(log_path, payload):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_log_entry(args, reference_image_paths, status, *, result=None, error_message=None):
    entry = {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "request": {
            "prompt": args.prompt,
            "model": args.model,
            "size": args.size,
            "temperature": args.temperature,
            "timeout": args.timeout,
            "reference_image_paths": list(reference_image_paths),
            "output_dir": args.output_dir,
            "file_name": args.file_name,
            "no_download": args.no_download,
        },
    }

    if result is not None:
        entry["result"] = result

    if error_message is not None:
        entry["error"] = error_message

    return entry


def http_json(url, *, method, headers, data=None, timeout=60.0):
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            text = decode_body(raw, resp.headers)
    except error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {text}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc.reason}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {text}") from exc


def build_chat_completions_url(base_url):
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1/chat/completions"):
        return normalized
    return f"{normalized}/v1/chat/completions"


def build_prompt(prompt, size):
    normalized_prompt = prompt.strip()
    if size and size != DEFAULT_SIZE:
        # The chat completions endpoint does not expose a native size field,
        # so we preserve the CLI contract by expressing the ratio in the prompt.
        return f"{normalized_prompt}\n\n请生成比例为 {size} 的图片。"
    return normalized_prompt


def resolve_reference_image_path(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise RuntimeError(
            f"Reference image path must be absolute: {raw_path}"
        )
    if not path.is_file():
        raise RuntimeError(
            f"Reference image path does not exist or is not a file: {raw_path}"
        )

    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        raise RuntimeError(
            f"Reference image path is not a supported image file: {raw_path}"
        )

    return path.resolve(), mime_type


def encode_image_as_data_url(path, mime_type):
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise RuntimeError(f"Failed to read reference image {path}: {exc}") from exc
    return f"data:{mime_type};base64,{encoded}"


def build_user_content(prompt, size, reference_image_paths):
    text_content = build_prompt(prompt, size)
    if not reference_image_paths:
        return text_content

    content = [{"type": "text", "text": text_content}]
    for raw_path in reference_image_paths:
        resolved_path, mime_type = resolve_reference_image_path(raw_path)
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": encode_image_as_data_url(resolved_path, mime_type),
                },
            }
        )
    return content


def request_image_completion(
    api_key,
    prompt,
    model,
    size,
    temperature,
    timeout,
    reference_image_paths=None,
):
    payload = {
        "temperature": temperature,
        "messages": [
            {
                "content": build_user_content(prompt, size, reference_image_paths or []),
                "role": "user",
            }
        ],
        "model": model,
        "stream": False,
    }
    return http_json(
        build_chat_completions_url(DEFAULT_BASE_URL),
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )


def extract_message_content(payload):
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            "Response did not include choices: "
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    first_choice = choices[0]
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(
            "Response choice did not include a message: "
            + json.dumps(first_choice, ensure_ascii=False, separators=(",", ":"))
        )

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            "Response message content was empty: "
            + json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        )

    return first_choice, content


def extract_urls_from_content(content):
    image_match = IMAGE_MARKDOWN_RE.search(content)
    image_url = image_match.group(1) if image_match else None

    download_match = DOWNLOAD_MARKDOWN_RE.search(content)
    download_url = download_match.group(1) if download_match else None

    if not image_url:
        for url in URL_RE.findall(content):
            if url != download_url:
                image_url = url
                break

    if not image_url and download_url:
        image_url = download_url

    if not image_url:
        raise RuntimeError(f"Response content did not include an image URL: {content}")

    return image_url, download_url


def guess_extension(image_url, content_type):
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type.startswith("image/"):
        guessed = mimetypes.guess_extension(normalized_type)
        if guessed:
            return guessed

    url_path = parse.urlparse(image_url).path
    ext = Path(url_path).suffix
    if ext:
        return ext.lower()
    return ".png"


def resolve_output_path(output_dir, file_name, image_url, headers, image_id):
    target_dir = (
        Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "tu-zi-nano"
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    if file_name:
        candidate = Path(file_name)
        if candidate.suffix:
            return target_dir / candidate.name
        ext = guess_extension(image_url, headers.get("Content-Type"))
        return target_dir / f"{candidate.name}{ext}"

    ext = guess_extension(image_url, headers.get("Content-Type"))
    return target_dir / f"{image_id}{ext}"


def download_image(image_url, output_dir=None, file_name=None, timeout=60.0, image_id="image"):
    req = request.Request(image_url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            output_path = resolve_output_path(
                output_dir,
                file_name,
                image_url,
                resp.headers,
                image_id,
            )
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Failed to download image: HTTP {exc.code}: {raw}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to download image: {exc.reason}") from exc

    output_path.write_bytes(data)
    return output_path.resolve()


def main():
    parser = build_parser()
    args = parser.parse_args()
    configure_stdio()
    log_path = resolve_log_path(args.log_file)
    reference_image_paths = args.reference_image_path or []

    try:
        api_key = require_api_key()
        response = request_image_completion(
            api_key,
            args.prompt,
            args.model,
            args.size,
            args.temperature,
            args.timeout,
            reference_image_paths,
        )
        first_choice, content = extract_message_content(response)
        image_url, download_url = extract_urls_from_content(content)

        response_id = response.get("id") or "image"
        result = {
            "id": response_id,
            "status": "completed",
            "image_url": image_url,
            "prompt": args.prompt,
            "size": args.size,
            "model": response.get("model", args.model),
            "finish_reason": first_choice.get("finish_reason"),
            "content": content,
        }

        if download_url:
            result["download_url"] = download_url

        if not args.no_download:
            saved_path = download_image(
                download_url or image_url,
                output_dir=args.output_dir,
                file_name=args.file_name,
                timeout=args.timeout,
                image_id=response_id,
            )
            result["saved_path"] = str(saved_path)

        result["log_path"] = str(log_path)
        append_generation_log(
            log_path,
            build_log_entry(args, reference_image_paths, "completed", result=result),
        )
        write_stdout(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        error_message = str(exc)
        try:
            append_generation_log(
                log_path,
                build_log_entry(
                    args,
                    reference_image_paths,
                    "failed",
                    error_message=error_message,
                ),
            )
        except Exception as log_exc:
            write_stderr(f"Failed to write generation log: {log_exc}")
        write_stderr(error_message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
