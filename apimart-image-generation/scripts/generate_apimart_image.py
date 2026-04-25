#!/usr/bin/env python3
import argparse
import base64
import json
import mimetypes
import os
import platform
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib import parse

import requests


DEFAULT_BASE_URL = "https://api.apimart.ai"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1:1"
DEFAULT_RESOLUTION = "1k"
DEFAULT_LANGUAGE = "zh"
DEFAULT_HTTP_TIMEOUT = 60.0
DEFAULT_GENERATE_TIMEOUT = 180.0
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_INITIAL_DELAY = 10.0
DEFAULT_USER_AGENT = (
    f"apimart-image-generation/1.0 "
    f"(Python {platform.python_version()}; requests {requests.__version__})"
)
MAX_REFERENCE_IMAGES = 16
VALID_SIZES = (
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "5:4",
    "4:5",
    "2:1",
    "1:2",
    "21:9",
    "9:21",
)
VALID_RESOLUTIONS = ("1k", "2k", "4k")
VALID_4K_SIZES = ("16:9", "9:16", "2:1", "1:2", "21:9", "9:21")
IN_PROGRESS_STATUSES = {"submitted", "pending", "processing", "in_progress"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
DEFAULT_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "logs" / "generation-history.jsonl"
)


class AppendReferenceAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        current = getattr(namespace, self.dest, None)
        if current is None:
            current = []
        if option_string == "--reference-image-path":
            kind = "path"
        else:
            kind = "url"
        current.append({"kind": kind, "value": values})
        setattr(namespace, self.dest, current)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Submit and poll APIMart GPT-Image-2 generation tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        help="Submit an image generation task and poll until completion.",
    )
    generate.add_argument("--prompt", required=True, help="Prompt text.")
    generate.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help="Aspect ratio. Example: 1:1 or 16:9.",
    )
    generate.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        help="Output resolution. Supported values: 1k, 2k, 4k.",
    )
    generate.add_argument(
        "--reference-image-path",
        dest="reference_inputs",
        action=AppendReferenceAction,
        help="Absolute path to a local reference image. Repeat to add more.",
    )
    generate.add_argument(
        "--reference-image-url",
        dest="reference_inputs",
        action=AppendReferenceAction,
        help="Public URL for a reference image. Repeat to add more.",
    )
    generate.add_argument(
        "--output-dir",
        help="Directory where the generated image should be downloaded.",
    )
    generate.add_argument(
        "--file-name",
        help="Optional output file name. Extension is inferred when possible.",
    )
    generate.add_argument(
        "--no-download",
        action="store_true",
        help="Return the image URL without downloading the file.",
    )
    generate.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_GENERATE_TIMEOUT,
        help="Total timeout in seconds for the full generate-and-poll workflow.",
    )
    generate.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Polling interval in seconds after the first task lookup.",
    )
    generate.add_argument(
        "--initial-delay",
        type=float,
        default=DEFAULT_INITIAL_DELAY,
        help="Delay in seconds before the first task lookup.",
    )
    generate.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="Language hint passed to the task status endpoint.",
    )
    generate.add_argument(
        "--log-file",
        help="Optional JSONL log file path. Defaults to logs/generation-history.jsonl.",
    )

    status = subparsers.add_parser(
        "status",
        help="Fetch the status for an existing APIMart task.",
    )
    status.add_argument("--task-id", required=True, help="APIMart task ID.")
    status.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="Language hint passed to the task status endpoint.",
    )
    status.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_HTTP_TIMEOUT,
        help="HTTP timeout in seconds for this request.",
    )

    return parser


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
        sys.stderr.buffer.write(text.encode("utf-8", errors="backslashreplace"))
    except Exception:
        print(text, file=sys.stderr, end="")


def require_api_key():
    api_key = os.environ.get("APIMART_API_KEY")
    if api_key:
        return api_key
    raise RuntimeError("Missing APIMART_API_KEY environment variable.")


def build_http_headers(extra_headers=None):
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def http_json(url, *, method, headers, data=None, timeout=DEFAULT_HTTP_TIMEOUT):
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=build_http_headers(headers),
            data=data,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    text = response.text
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} for {url}: {text}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Non-JSON response from {url}: {text}") from exc


def resolve_log_path(raw_path=None):
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return DEFAULT_LOG_PATH


def append_generation_log(log_path, payload):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def validate_size(size):
    if size not in VALID_SIZES:
        allowed = ", ".join(VALID_SIZES)
        raise RuntimeError(
            f"Unsupported size '{size}'. Supported ratios: {allowed}"
        )


def normalize_resolution(resolution):
    return (resolution or "").strip().lower()


def validate_resolution(resolution):
    if resolution not in VALID_RESOLUTIONS:
        allowed = ", ".join(VALID_RESOLUTIONS)
        raise RuntimeError(
            f"Unsupported resolution '{resolution}'. Supported values: {allowed}"
        )


def validate_size_resolution_pair(size, resolution):
    if resolution == "4k" and size not in VALID_4K_SIZES:
        allowed = ", ".join(VALID_4K_SIZES)
        raise RuntimeError(
            f"Unsupported size '{size}' for resolution '4k'. "
            f"Supported 4k ratios: {allowed}"
        )


def validate_timeout_value(name, value):
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than 0.")


def validate_task_id(task_id):
    if not task_id or not task_id.strip():
        raise RuntimeError("task_id must not be empty.")
    return task_id.strip()


def resolve_reference_image_path(raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        raise RuntimeError(f"Reference image path must be absolute: {raw_path}")
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


def validate_reference_image_url(raw_url):
    parsed = parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Reference image URL must be http/https: {raw_url}")
    return raw_url


def encode_image_as_data_url(path, mime_type):
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise RuntimeError(f"Failed to read reference image {path}: {exc}") from exc
    return f"data:{mime_type};base64,{encoded}"


def build_image_urls(reference_inputs):
    image_urls = []
    sanitized_inputs = []

    for item in reference_inputs or []:
        kind = item["kind"]
        raw_value = item["value"]
        if kind == "path":
            resolved_path, mime_type = resolve_reference_image_path(raw_value)
            image_urls.append(encode_image_as_data_url(resolved_path, mime_type))
            sanitized_inputs.append(
                {"kind": "path", "value": str(resolved_path)}
            )
        else:
            image_url = validate_reference_image_url(raw_value)
            image_urls.append(image_url)
            sanitized_inputs.append({"kind": "url", "value": image_url})

    if len(image_urls) > MAX_REFERENCE_IMAGES:
        raise RuntimeError(
            f"Reference image count exceeds max {MAX_REFERENCE_IMAGES}: "
            f"{len(image_urls)}"
        )

    return image_urls, sanitized_inputs


def build_generation_payload(prompt, size, resolution, image_urls):
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": prompt.strip(),
        "n": 1,
        "size": size,
        "resolution": resolution,
    }
    if not payload["prompt"]:
        raise RuntimeError("prompt must not be empty.")
    if image_urls:
        payload["image_urls"] = image_urls
    return payload


def submit_generation(api_key, payload):
    return http_json(
        f"{DEFAULT_BASE_URL}/v1/images/generations",
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=DEFAULT_HTTP_TIMEOUT,
    )


def extract_submission(submit_payload):
    data = submit_payload.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError(
            "Submit response did not include data array: "
            + json.dumps(submit_payload, ensure_ascii=False, separators=(",", ":"))
        )

    first = data[0]
    if not isinstance(first, dict):
        raise RuntimeError(
            "Submit response item was not an object: "
            + json.dumps(first, ensure_ascii=False, separators=(",", ":"))
        )

    task_id = first.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise RuntimeError(
            "Submit response did not include task_id: "
            + json.dumps(first, ensure_ascii=False, separators=(",", ":"))
        )

    return {"status": first.get("status"), "task_id": task_id}


def fetch_task_status(api_key, task_id, language, timeout):
    query = parse.urlencode({"language": language})
    url = f"{DEFAULT_BASE_URL}/v1/tasks/{parse.quote(task_id)}?{query}"
    return http_json(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout=timeout,
    )


def extract_first_image(result):
    if not isinstance(result, dict):
        return None, None

    images = result.get("images")
    if not isinstance(images, list) or not images:
        return None, None

    first_image = images[0]
    if not isinstance(first_image, dict):
        return None, None

    urls = first_image.get("url")
    image_url = None
    if isinstance(urls, list) and urls:
        candidate = urls[0]
        if isinstance(candidate, str) and candidate.strip():
            image_url = candidate

    expires_at = first_image.get("expires_at")
    return image_url, expires_at


def normalize_task_snapshot(task_payload):
    data = task_payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(
            "Task response did not include data object: "
            + json.dumps(task_payload, ensure_ascii=False, separators=(",", ":"))
        )

    image_url, expires_at = extract_first_image(data.get("result"))
    snapshot = {
        "task_id": data.get("id"),
        "status": data.get("status"),
        "progress": data.get("progress"),
        "created": data.get("created"),
        "completed": data.get("completed"),
        "actual_time": data.get("actual_time"),
        "estimated_time": data.get("estimated_time"),
    }
    if image_url:
        snapshot["image_url"] = image_url
    if expires_at is not None:
        snapshot["expires_at"] = expires_at
    if "error" in data:
        snapshot["error"] = data["error"]
    return snapshot


def poll_task_until_terminal(api_key, task_id, language, initial_delay, poll_interval, timeout):
    deadline = time.monotonic() + timeout
    history = []
    if initial_delay > 0:
        time.sleep(initial_delay)

    while True:
        task_payload = fetch_task_status(
            api_key,
            task_id,
            language,
            timeout=min(DEFAULT_HTTP_TIMEOUT, max(timeout, 1.0)),
        )
        snapshot = normalize_task_snapshot(task_payload)
        history.append(
            {
                "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": snapshot.get("status"),
                "progress": snapshot.get("progress"),
            }
        )

        status = snapshot.get("status")
        if status in TERMINAL_STATUSES:
            return task_payload, snapshot, history

        if status not in IN_PROGRESS_STATUSES:
            raise RuntimeError(
                "Task returned unknown non-terminal status: "
                + json.dumps(snapshot, ensure_ascii=False)
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Timed out waiting for task {task_id}. Last status: {status}"
            )
        time.sleep(min(poll_interval, remaining))


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
        Path(output_dir)
        if output_dir
        else Path(tempfile.gettempdir()) / "apimart-image-generation"
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


def download_image(image_url, output_dir=None, file_name=None, timeout=DEFAULT_HTTP_TIMEOUT, image_id="image"):
    try:
        with requests.get(
            image_url,
            headers=build_http_headers({"Accept": "image/*,*/*;q=0.8"}),
            timeout=timeout,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Failed to download image: HTTP {response.status_code}: {response.text}"
                )
            output_path = resolve_output_path(
                output_dir,
                file_name,
                image_url,
                response.headers,
                image_id,
            )
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to download image: {exc}") from exc

    return output_path.resolve()


def build_log_entry(
    *,
    args,
    request_meta,
    status,
    submit_response=None,
    poll_history=None,
    task_response=None,
    result=None,
    error_message=None,
):
    entry = {
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "request": request_meta,
    }
    if submit_response is not None:
        entry["submit_response"] = submit_response
    if poll_history is not None:
        entry["poll_history"] = poll_history
    if task_response is not None:
        entry["task_response"] = task_response
    if result is not None:
        entry["result"] = result
    if error_message is not None:
        entry["error"] = error_message
    return entry


def run_generate(args):
    log_path = resolve_log_path(args.log_file)
    submit_response = None
    poll_history = []
    task_response = None
    resolution = normalize_resolution(args.resolution)
    request_meta = {
        "prompt": args.prompt,
        "model": DEFAULT_MODEL,
        "n": 1,
        "size": args.size,
        "resolution": resolution,
        "language": args.language,
        "timeout": args.timeout,
        "poll_interval": args.poll_interval,
        "initial_delay": args.initial_delay,
        "reference_image_count": None,
        "reference_images": args.reference_inputs or [],
        "output_dir": args.output_dir,
        "file_name": args.file_name,
        "no_download": args.no_download,
    }
    try:
        validate_size(args.size)
        validate_resolution(resolution)
        validate_size_resolution_pair(args.size, resolution)
        validate_timeout_value("timeout", args.timeout)
        validate_timeout_value("poll-interval", args.poll_interval)
        if args.initial_delay < 0:
            raise RuntimeError("initial-delay must be greater than or equal to 0.")

        image_urls, sanitized_inputs = build_image_urls(args.reference_inputs or [])
        request_meta["reference_image_count"] = len(sanitized_inputs)
        request_meta["reference_images"] = sanitized_inputs
        api_key = require_api_key()
        payload = build_generation_payload(
            args.prompt,
            args.size,
            resolution,
            image_urls,
        )
        submit_response = submit_generation(api_key, payload)
        submission = extract_submission(submit_response)
        task_id = submission["task_id"]
        task_response, snapshot, poll_history = poll_task_until_terminal(
            api_key,
            task_id,
            args.language,
            args.initial_delay,
            args.poll_interval,
            args.timeout,
        )

        if snapshot.get("status") == "completed":
            result = {
                "task_id": task_id,
                "status": snapshot.get("status"),
                "progress": snapshot.get("progress"),
                "prompt": args.prompt,
                "size": args.size,
                "resolution": resolution,
                "model": DEFAULT_MODEL,
                "reference_image_count": len(sanitized_inputs),
                "reference_images": sanitized_inputs,
                "image_url": snapshot.get("image_url"),
                "expires_at": snapshot.get("expires_at"),
                "created": snapshot.get("created"),
                "completed": snapshot.get("completed"),
                "actual_time": snapshot.get("actual_time"),
                "estimated_time": snapshot.get("estimated_time"),
                "submit_status": submission.get("status"),
                "poll_history": poll_history,
                "log_path": str(log_path),
            }

            if not result.get("image_url"):
                raise RuntimeError(
                    "Completed task did not include data.result.images[0].url[0]."
                )

            if not args.no_download:
                saved_path = download_image(
                    result["image_url"],
                    output_dir=args.output_dir,
                    file_name=args.file_name,
                    timeout=DEFAULT_HTTP_TIMEOUT,
                    image_id=task_id,
                )
                result["saved_path"] = str(saved_path)

            append_generation_log(
                log_path,
                build_log_entry(
                    args=args,
                    request_meta=request_meta,
                    status="completed",
                    submit_response=submit_response,
                    poll_history=poll_history,
                    task_response=task_response,
                    result=result,
                ),
            )
            write_stdout(json.dumps(result, ensure_ascii=False))
            return 0

        error_payload = snapshot.get("error")
        if isinstance(error_payload, dict):
            error_message = error_payload.get("message") or json.dumps(
                error_payload, ensure_ascii=False
            )
        elif error_payload is not None:
            error_message = str(error_payload)
        else:
            error_message = f"Task ended with status {snapshot.get('status')}"
        raise RuntimeError(error_message)
    except Exception as exc:
        error_message = str(exc)
        try:
            append_generation_log(
                log_path,
                build_log_entry(
                    args=args,
                    request_meta=request_meta,
                    status="failed",
                    submit_response=submit_response,
                    poll_history=poll_history,
                    task_response=task_response,
                    error_message=error_message,
                ),
            )
        except Exception as log_exc:
            write_stderr(f"Failed to write generation log: {log_exc}")
        write_stderr(error_message)
        return 1


def run_status(args):
    try:
        validate_timeout_value("timeout", args.timeout)
        api_key = require_api_key()
        task_id = validate_task_id(args.task_id)
        task_response = fetch_task_status(api_key, task_id, args.language, args.timeout)
        snapshot = normalize_task_snapshot(task_response)
        write_stdout(json.dumps(snapshot, ensure_ascii=False))
        return 0
    except Exception as exc:
        write_stderr(str(exc))
        return 1


def main():
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "generate":
            return run_generate(args)
        if args.command == "status":
            return run_status(args)
        parser.error(f"Unsupported command: {args.command}")
        return 2
    except Exception as exc:
        write_stderr(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
