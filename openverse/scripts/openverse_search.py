#!/usr/bin/env python3
"""Search Openverse images and audio with OAuth credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://api.openverse.org/v1"
USER_AGENT = "Codex Openverse skill/1.0"


class OpenverseError(RuntimeError):
    """Raised for expected Openverse CLI failures."""


def env_required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise OpenverseError(
            f"Missing {name}. Set OPENVERSE_CLIENT_ID and "
            "OPENVERSE_CLIENT_SECRET before using this skill."
        )
    return value


def base_url() -> str:
    return os.environ.get("OPENVERSE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def api_url(path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{base_url()}/{path.lstrip('/')}"
    if params:
        clean_params: dict[str, str] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                if not value:
                    continue
                clean_params[key] = "true"
            else:
                clean_params[key] = str(value)
        if clean_params:
            url = f"{url}?{urllib.parse.urlencode(clean_params)}"
    return url


def parse_json_response(response: urllib.response.addinfourl) -> Any:
    payload = response.read().decode("utf-8")
    if not payload:
        return None
    return json.loads(payload)


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> Any:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return parse_json_response(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = body.strip() or exc.reason
        raise OpenverseError(f"HTTP {exc.code} for {url}: {message}") from exc
    except urllib.error.URLError as exc:
        raise OpenverseError(f"Request failed for {url}: {exc.reason}") from exc


def fetch_token() -> str:
    client_id = env_required("OPENVERSE_CLIENT_ID")
    client_secret = env_required("OPENVERSE_CLIENT_SECRET")
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    token_data = request_json(
        api_url("/auth_tokens/token/"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
    )

    token = token_data.get("access_token") if isinstance(token_data, dict) else None
    if not token:
        raise OpenverseError("Openverse token response did not include access_token.")
    return str(token)


def media_endpoint(media: str) -> str:
    if media == "image":
        return "images"
    if media == "audio":
        return "audio"
    raise OpenverseError(f"Unsupported media type: {media}")


def authed_get(path: str, params: dict[str, Any] | None = None) -> Any:
    token = fetch_token()
    return request_json(
        api_url(path, params),
        headers={"Authorization": f"Bearer {token}"},
    )


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def validate_search_args(args: argparse.Namespace) -> None:
    search_fields = [args.q, args.tags, args.title, args.creator]
    if not any(search_fields):
        raise OpenverseError(
            "Provide --query, --tags, --title, or --creator for search."
        )
    if args.q and (args.tags or args.title):
        raise OpenverseError("--query cannot be combined with --tags or --title.")
    if args.q and len(args.q) > 200:
        raise OpenverseError("--query must be 200 characters or fewer.")
    if args.media == "image" and (args.length or args.peaks):
        raise OpenverseError("--length and --peaks are audio-only filters.")
    if args.media == "audio" and (args.aspect_ratio or args.size):
        raise OpenverseError("--aspect-ratio and --size are image-only filters.")


def search(args: argparse.Namespace) -> Any:
    validate_search_args(args)
    params = {
        "q": args.q,
        "page": args.page,
        "page_size": args.page_size,
        "source": args.source,
        "excluded_source": args.excluded_source,
        "tags": args.tags,
        "title": args.title,
        "creator": args.creator,
        "license": args.license,
        "license_type": args.license_type,
        "filter_dead": args.filter_dead,
        "extension": args.extension,
        "mature": args.mature,
        "category": args.category,
        "aspect_ratio": args.aspect_ratio if args.media == "image" else None,
        "size": args.size if args.media == "image" else None,
        "length": args.length if args.media == "audio" else None,
        "peaks": args.peaks if args.media == "audio" else None,
    }
    return authed_get(f"/{media_endpoint(args.media)}/", params)


def detail(args: argparse.Namespace) -> Any:
    identifier = urllib.parse.quote(args.id, safe="")
    return authed_get(f"/{media_endpoint(args.media)}/{identifier}/")


def related(args: argparse.Namespace) -> Any:
    identifier = urllib.parse.quote(args.id, safe="")
    params = {"page": args.page, "page_size": args.page_size}
    return authed_get(f"/{media_endpoint(args.media)}/{identifier}/related/", params)


def duration_label(item: dict[str, Any]) -> str | None:
    duration = item.get("duration")
    if duration is None:
        return None
    try:
        seconds = float(duration) / 1000
    except (TypeError, ValueError):
        return str(duration)
    if seconds >= 60:
        minutes = int(seconds // 60)
        remainder = int(round(seconds % 60))
        return f"{minutes}:{remainder:02d}"
    return f"{seconds:.1f}s"


def dimensions_label(item: dict[str, Any]) -> str | None:
    width = item.get("width")
    height = item.get("height")
    if width and height:
        return f"{width}x{height}"
    return None


def markdown_item(item: dict[str, Any], index: int | None = None) -> str:
    title = item.get("title") or "(untitled)"
    prefix = f"{index}. " if index is not None else "## "
    lines = [f"{prefix}{title}"]

    fields = [
        ("ID", item.get("id")),
        ("Creator", item.get("creator")),
        ("Provider", item.get("provider") or item.get("source")),
        ("License", license_label(item)),
        ("Dimensions", dimensions_label(item)),
        ("Duration", duration_label(item)),
        ("Media URL", item.get("url")),
        ("Thumbnail", item.get("thumbnail")),
        ("Waveform", item.get("waveform")),
        ("Landing page", item.get("foreign_landing_url")),
        ("License URL", item.get("license_url")),
        ("Attribution", item.get("attribution")),
    ]

    for label, value in fields:
        if value:
            lines.append(f"   - {label}: {value}")
    return "\n".join(lines)


def license_label(item: dict[str, Any]) -> str | None:
    license_name = item.get("license")
    license_version = item.get("license_version")
    if license_name and license_version:
        return f"{license_name} {license_version}"
    if license_name:
        return str(license_name)
    return None


def render_markdown(data: Any) -> str:
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        result_count = data.get("result_count", "?")
        page = data.get("page", "?")
        page_count = data.get("page_count", "?")
        page_size = data.get("page_size", "?")
        lines = [
            f"Found {result_count} results. Page {page} of {page_count}. Page size {page_size}.",
            "",
        ]
        for index, item in enumerate(data["results"], start=1):
            if isinstance(item, dict):
                lines.append(markdown_item(item, index))
                lines.append("")
        warnings = data.get("warnings")
        if warnings:
            lines.append("Warnings:")
            lines.append(json.dumps(warnings, ensure_ascii=False, indent=2))
        return "\n".join(lines).strip() + "\n"

    if isinstance(data, dict):
        return markdown_item(data) + "\n"

    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def output(data: Any, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    if output_format == "markdown":
        sys.stdout.write(render_markdown(data))
        return
    raise OpenverseError(f"Unsupported output format: {output_format}")


def add_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format. Defaults to raw JSON.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Openverse images and audio using OAuth credentials.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Required environment variables:
              OPENVERSE_CLIENT_ID
              OPENVERSE_CLIENT_SECRET

            Examples:
              openverse_search.py search --media image --query "red fox" --format markdown
              openverse_search.py search --media audio --query "rain ambience" --license-type commercial
              openverse_search.py detail --media image --id "<openverse-id>" --format markdown
              openverse_search.py related --media audio --id "<openverse-id>" --page-size 5
            """
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser(
        "search",
        help="Search image or audio results.",
    )
    search_parser.add_argument("--media", choices=("image", "audio"), required=True)
    search_parser.add_argument("-q", "--query", dest="q", help="Search query.")
    search_parser.add_argument("--page", type=positive_int, default=1)
    search_parser.add_argument("--page-size", type=positive_int, default=5)
    search_parser.add_argument("--source", help="Comma-separated source names.")
    search_parser.add_argument(
        "--excluded-source",
        help="Comma-separated source names to exclude.",
    )
    search_parser.add_argument("--tags", help="Tag-only fuzzy search.")
    search_parser.add_argument("--title", help="Title-only fuzzy search.")
    search_parser.add_argument("--creator", help="Creator-only fuzzy search.")
    search_parser.add_argument("--license", help="Comma-separated license codes.")
    search_parser.add_argument(
        "--license-type",
        choices=("all", "all-cc", "commercial", "modification"),
        help="License type filter.",
    )
    search_parser.add_argument(
        "--filter-dead",
        choices=("true", "false"),
        help="Control whether dead links are filtered.",
    )
    search_parser.add_argument("--extension", help="Comma-separated file extensions.")
    search_parser.add_argument(
        "--mature",
        action="store_true",
        help="Include mature or sensitive results when supported by the API.",
    )
    search_parser.add_argument("--category", help="Media category filter.")
    search_parser.add_argument(
        "--aspect-ratio",
        choices=("square", "tall", "wide"),
        help="Image-only aspect ratio filter.",
    )
    search_parser.add_argument(
        "--size",
        choices=("large", "medium", "small"),
        help="Image-only size filter.",
    )
    search_parser.add_argument(
        "--length",
        choices=("long", "medium", "short", "shortest"),
        help="Audio-only length filter.",
    )
    search_parser.add_argument(
        "--peaks",
        action="store_true",
        help="Audio-only option to include waveform peaks.",
    )
    add_output_arg(search_parser)
    search_parser.set_defaults(func=search)

    detail_parser = subparsers.add_parser("detail", help="Fetch one media item.")
    detail_parser.add_argument("--media", choices=("image", "audio"), required=True)
    detail_parser.add_argument("--id", required=True, help="Openverse media ID.")
    add_output_arg(detail_parser)
    detail_parser.set_defaults(func=detail)

    related_parser = subparsers.add_parser(
        "related",
        help="Fetch related media items.",
    )
    related_parser.add_argument("--media", choices=("image", "audio"), required=True)
    related_parser.add_argument("--id", required=True, help="Openverse media ID.")
    related_parser.add_argument("--page", type=positive_int, default=1)
    related_parser.add_argument("--page-size", type=positive_int, default=5)
    add_output_arg(related_parser)
    related_parser.set_defaults(func=related)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        data = args.func(args)
        output(data, args.format)
        return 0
    except OpenverseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
