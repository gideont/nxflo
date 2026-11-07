# Publishing an article

Keep **Stale by Thursday** as the starred article on `articles.html` unless explicitly asked to change it. Add each new publication as a card in `.article-library-grid`; put the newest card first. The library grows independently of the featured report.

For each new article (normally every one or two weeks):

1. Add the approved PDF to `articles/`. Read it before writing the summary. Confirm the title, edition, page count, and file size; do not invent a publication day when only a month is supplied.
2. Add a descriptive root HTML page, using `etl-dashboard-process-playbook.html` as the layout reference. Keep the shared SEO, header, and footer includes. Include a useful summary, topics in natural language, chart previews with accessible descriptions and source page numbers, and direct PDF downloads. Label illustrative figures honestly.
3. Export the cover and selected charts to optimized WebP files in `images/articles/`. Keep labels legible and link charts to their full-size assets.
4. Add a `Page` entry in `lib/seo.py` with a unique title, summary, cover, and `navigation="articles.html"`. Set relevant `keywords` and the article headline. Set `article_pdf` to that article's PDF path for the structured download metadata. The registry automatically adds indexable pages to the generated sitemap.
5. Add the card to `articles.html`, linking the summary page and PDF. Add new article assets to `tests/check_deployment.py` for exact live-file checks.
6. Run `python3 build.py`, the site and SEO unit checks, and the article browser checks. Inspect at 1440px, 375px, 320px, and 430px; check images, downloads, menus, and overflow.
7. Run `bash 1_build_docker.sh`, then `bash 2_deploy_docker.sh`. Verify the page, original PDF, images, and sitemap at `https://www.nxflo.com/` with `PYTHONPATH=. python3 tests/check_deployment.py --url https://www.nxflo.com/`.

Edit source files only; `dist/` and the sitemap are generated. There is no need to change the shared navigation for each publication.
