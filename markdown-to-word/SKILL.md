---
name: markdown-to-word
description: Convert Markdown files (.md) into Microsoft Word documents (.docx) with a pure Python converter. Use when Codex needs to turn Markdown into a formal Chinese Word document, generate a DOCX from Markdown content, preserve common Markdown structure in Word, or run a local Markdown-to-DOCX workflow without Pandoc.
---

# Markdown To Word

## Workflow

1. Read `references/formats/formal-zh.md` before converting so the document style expectations are in context.
2. Use `scripts/md_to_docx.py` to convert the Markdown file.
3. Open or inspect the generated DOCX when the task requires verification.

The bundled converter does not use Pandoc. It parses Markdown with `markdown-it-py` and writes Word output with `python-docx`.

## Quick Start

Run the converter from any working directory:

```powershell
python "<skill>\scripts\md_to_docx.py" convert "C:\path\input.md" --output "C:\path\output.docx"
```

Default behavior:

- Use `--format formal-zh`.
- Insert a Word TOC field with `--toc`.
- Number headings with `--number-headings`.
- Resolve relative images from the Markdown file's absolute directory and download HTTP/HTTPS images before embedding them.
- Normalize heading levels so the shallowest Markdown heading becomes Word `Heading 1`.

Useful options:

```powershell
python "<skill>\scripts\md_to_docx.py" convert "C:\path\input.md" --output "C:\path\output.docx" --resource-path "C:\path\assets" --toc-depth 3 --json
```

## Format

Only one built-in format is currently available:

- `formal-zh`: A4 formal Chinese document defaults with Chinese font setup, heading styles, numbered headings, a TOC field with explicit TOC indentation styles, grid tables, readable paragraph spacing, blockquote styling, and shaded code blocks.

Read `references/formats/formal-zh.md` for the style description. The reference is guidance for Codex; the script applies the built-in defaults directly and does not parse the Markdown reference file.

## Converter Capabilities

The script supports:

- YAML front matter metadata such as `title`, `author`, and `date`.
- Headings, paragraphs, bold, italic, inline code, links, ordered lists, unordered lists, nested lists, tables, fenced code blocks, blockquotes, horizontal rules, local images, and remote HTTP/HTTPS images.
- Heading level normalization so documents whose first content heading is `##` still produce left-aligned top-level TOC entries.
- Relative image lookup from the Markdown file's absolute directory, plus optional `--resource-path` values.
- Percent-decoded local image paths, such as `%E5%9B%BE%E7%89%87/a.png`, before filesystem lookup.
- Remote image download and embedding with warnings for failed, unsupported, or oversized images.
- Machine-readable CLI output with `--json`.

If an image cannot be inserted, the script writes a readable placeholder and reports a warning.
