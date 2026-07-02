# kiipeilyareena RSS

Scrapes news from Kiipeilyareena and generates an RSS feed.

## Setup

```bash
uv sync
uv run python scraper.py
```

## GitHub Actions

The workflow runs hourly and commits `feed.xml` to the repo. To serve on GitHub Pages:

1. Push the repo to GitHub
2. Go to Settings → Pages → select `main` branch, root folder `/`
3. The feed will be available at `https://<user>.github.io/<repo>/feed.xml`

## Tech

- Python 3.11+ with `uv`
- `beautifulsoup4` for HTML parsing
- `feedgenerator` for RSS 2.0 output
