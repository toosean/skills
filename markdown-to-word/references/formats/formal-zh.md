# formal-zh

`formal-zh` is the default style for converting Markdown into a formal Chinese Word document. It is intended for reports, proposals, technical summaries, meeting materials, and other documents that need a clean `.docx` deliverable rather than a Markdown-like export.

## Page Layout

- Use A4 paper.
- Use readable formal margins suitable for printing and review.
- Keep the body text spacious enough for Chinese paragraphs while avoiding excessive whitespace.

## Typography

- Use Song-style Chinese body text with a Latin serif fallback.
- Use Hei-style Chinese headings.
- Use a monospace Latin font for code.
- Keep body paragraphs at a normal report-reading size with first-line indentation.

## Structure

- When `--title` is provided, insert a first-page cover before the TOC and body content.
- Put the provided title as the main cover text in the middle area of the page.
- Do not add a separate top title, year line, or `封` / `面` placeholder text.
- Put `编制单位：...` near the lower center when an `author` value exists in Markdown front matter.
- Put `编制日期：YYYY年M月D日` near the lower center using the conversion date.
- Insert a Word table-of-contents field near the beginning when TOC is enabled.
- Keep TOC level 1 aligned to the document text area, indent deeper TOC levels modestly, and use right-aligned dotted page-number tabs.
- Normalize the shallowest Markdown heading level to Word Heading 1 so top-level TOC entries are not accidentally indented.
- Number headings by default.
- Preserve Markdown hierarchy through Word heading styles.
- Keep metadata such as title, author, and date at the beginning of the document when provided in YAML front matter.

## Content Styling

- Render tables with visible grid borders and a lightly shaded header row.
- Render fenced code blocks with monospace text and light shading.
- Render blockquotes as indented muted text.
- Render links as clickable Word hyperlinks.
- Insert local images when they can be resolved from the Markdown file's absolute directory or `--resource-path`.
- Decode percent-encoded local image paths before resolving them on disk.
- Download and embed remote HTTP/HTTPS images when referenced by Markdown image syntax.
