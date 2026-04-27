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
- Resolve relative images from the Markdown file directory.

Useful options:

```powershell
python "<skill>\scripts\md_to_docx.py" convert "C:\path\input.md" --output "C:\path\output.docx" --resource-path "C:\path\assets" --toc-depth 3 --json
```

## Format

Only one built-in format is currently available:

- `formal-zh`: A4 formal Chinese document defaults with Chinese font setup, heading styles, numbered headings, a TOC field, grid tables, readable paragraph spacing, blockquote styling, and shaded code blocks.

Read `references/formats/formal-zh.md` for the style description. The reference is guidance for Codex; the script applies the built-in defaults directly and does not parse the Markdown reference file.

## Converter Capabilities

The script supports:

- YAML front matter metadata such as `title`, `author`, and `date`.
- Headings, paragraphs, bold, italic, inline code, links, ordered lists, unordered lists, nested lists, tables, fenced code blocks, blockquotes, horizontal rules, and local images.
- Relative image lookup through the Markdown file directory and optional `--resource-path` values.
- Machine-readable CLI output with `--json`.

Remote images are not downloaded by the converter. If an image cannot be inserted, the script writes a readable placeholder and reports a warning.
