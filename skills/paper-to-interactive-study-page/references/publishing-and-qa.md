# Publication and browser QA

Read this only when the user requests publication, replacement of a live page, or deployment troubleshooting.

## Authorization boundary

- A request to create a local HTML file does not authorize publication.
- A request to publish authorizes the minimum remote writes needed for the named site or repository, not unrelated refactors, repository creation, or deletion.
- Preserve unrelated files and existing URLs. Prefer redirects for superseded public paths when bookmarks may exist.
- Never commit or push through the shell unless the user has authorized that workflow. Use the available repository connector when it is the established publication path.

## GitHub Pages replacement

1. Identify the exact repository, branch, and target path. For a root Pages site this is commonly `index.html`, but verify instead of guessing.
2. Fetch the current file and its blob SHA immediately before replacement.
3. Compare the intended local artifact with the fetched content. Skip a no-op write when they are identical.
4. Replace only the target file with a descriptive commit message.
5. Wait for Pages deployment, then download the public URL with a cache-busting query.
6. Compare SHA-256 hashes of the local artifact and downloaded response. A successful API write alone is not deployment verification.
7. Load the public page in a browser at desktop and mobile widths; verify the rendered DOM, not only the HTTP status.

## Required browser checks

- Approximately 390 × 844: document scroll width must not exceed viewport width; wide tables scroll inside their wrappers.
- Approximately 1440 px: map, statistics, and long-form text remain readable without excessive line length.
- Mermaid available: one SVG is present, expected nodes are keyboard-focusable, loading status is hidden.
- Mermaid unavailable: after the configured timeout, loading state is replaced by retry controls and a text outline; the page never waits indefinitely.
- Glossary: every term opens the matching explanation and focus returns to the trigger after closing.
- Discussions: individual disclosure controls and expand/collapse-all controls work.
- Easy read: generated table of contents matches section headings; font controls clamp at their stated minimum and maximum and do not change the rest of the page.
- Hash links land below the sticky header.
- Print preview does not hide substantive discussion or easy-read content.

Report the public URL, the local source file, the commit identifier when available, and the observable checks that passed. If deployment remains stale, distinguish repository state from CDN state and do not claim the public page is updated until verified.
