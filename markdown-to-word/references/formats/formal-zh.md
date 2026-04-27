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

- Insert a Word table-of-contents field near the beginning when TOC is enabled.
- Number headings by default.
- Preserve Markdown hierarchy through Word heading styles.
- Keep metadata such as title, author, and date at the beginning of the document when provided in YAML front matter.

## Content Styling

- Render tables with visible grid borders and a lightly shaded header row.
- Render fenced code blocks with monospace text and light shading.
- Render blockquotes as indented muted text.
- Render links as clickable Word hyperlinks.
- Insert local images when they can be resolved from the Markdown file directory or `--resource-path`.
