# Ukraine Archive — web app

An Astro static site that presents the Ukraine content as a browsable archive,
styled with a Vercel-inspired design language (Tailwind CSS v4 + Geist).

## Data flow

Content comes from the repo-root `content.json` (paraphrased entries) and
`archive/manifest.json`. The `sync-data` script copies them into `src/data/`
before every `dev`/`build`, so regenerating those files and re-running the app
picks up the new content automatically.

```
python paraphrase_to_json.py   # (repo root) regenerate content.json
cd web && npm run build         # sync-data runs automatically
```

## Commands

```bash
npm install      # install dependencies
npm run dev      # local dev server
npm run build    # type-check (astro check) + static build to dist/
npm run preview  # preview the built site
```

## Structure

- `src/styles/global.css` — design tokens (`@theme`), mesh gradient, base styles.
- `src/layouts/Base.astro` — page shell, skip link, header/footer.
- `src/lib/data.ts` — loads content, groups into sections, exposes helpers.
- `src/pages/index.astro` — home (hero, stats band, section grid).
- `src/pages/sections/[id].astro` — one page per section.
- `src/pages/topics/[id].astro` — article page with table of contents.
- `src/pages/browse.astro` — searchable/filterable index (URL-synced).

## Design

Follows the Vercel design language: ink-on-near-white canvas, a single black
pill primary CTA, a hero-only mesh gradient, Geist/Geist Mono type, stacked
calm shadows, and a polarity-flipped ink stats band. Reviewed against the
Vercel Web Interface Guidelines (accessibility, focus, typography, motion).
