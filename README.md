# All About Ukraine

Source material about Ukraine (scraped from Britannica) lives in `data-ukraine/`.
This repo includes a script that organizes it into a clean, sectioned index.

## Indexing script

`build_index.py` scans every markdown file in `data-ukraine/`, uses the OpenAI
API to categorize each document into a fixed set of sections (and to generate a
clean title + one-line summary), then writes:

- `INDEX.md` — a human-readable, section-by-section index.
- `index.json` — the same data, machine-readable.

The script is **duplicate-aware**: it hashes content, analyzes each unique body
only once, and flags files that share identical content.

### Setup

```bash
pip install -r requirements.txt
```

Add your key to `.env` (already git-ignored):

```
OPENAI_API_KEY=sk-...
```

### Run

```bash
python build_index.py
```

Optional environment overrides:

| Variable        | Default        | Purpose                          |
| --------------- | -------------- | -------------------------------- |
| `DATA_DIR`      | `data-ukraine` | Folder to scan                   |
| `OPENAI_MODEL`  | `gpt-4o-mini`  | Model used for classification    |
| `MAX_WORKERS`   | `6`            | Concurrent API requests          |

## Paraphrasing script

`paraphrase_to_json.py` reads every markdown file, strips all links/images and
any Britannica references or boilerplate, then uses the OpenAI API to paraphrase
the text in fresh wording while preserving every fact, figure, and date. Output
is `content.json`, structured for the website:

```json
{
  "entries": [
    {
      "id": "geography-and-climate-of-ukraine",
      "source_file": "Ukraine - Soils, Climate, Agriculture  Britannica.md",
      "section": "Land & Geography",
      "tags": ["ukraine", "geography", ...],
      "title": "...",
      "summary": "...",
      "sections": [{ "heading": "...", "paragraphs": ["...", "..."] }],
      "body_group": "<hash>"
    }
  ]
}
```

It is duplicate-aware (paraphrases each unique body once, reuses the result for
every file that shares it). Run it with:

```bash
python paraphrase_to_json.py
```

> `source_file` retains the original filename (which contains "Britannica") purely
> as provenance for joining with `archive/manifest.json`. The paraphrased content
> itself contains no Britannica references or links.

## Note on the current data

The current scrape captured only **2 unique articles** (the main "Ukraine"
country article and the "Russia–Ukraine War" article) saved under 44 different
topical filenames. The filenames describe the intended sections, but the bodies
are duplicated. Re-scraping is recommended to obtain the distinct content.
