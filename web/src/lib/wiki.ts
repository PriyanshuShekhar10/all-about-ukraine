import indexJson from "@/data/wiki/index.json";
import graphJson from "@/data/wiki/graph.json";
import redirectsJson from "@/data/wiki/redirects.json";

export interface WikiSource {
  title: string;
  url: string;
  license: string;
}

export interface InfoboxField {
  label: string;
  value: string;
  source?: string;
}

export interface WikiInfobox {
  label: string;
  fields: InfoboxField[];
}

export interface WikiSection {
  heading: string;
  paragraphs: string[];
}

export interface WikiPage {
  qid: string;
  slug: string;
  title: string;
  type: string;
  category: string;
  aliases: string[];
  infobox: WikiInfobox;
  summary: string;
  sections: WikiSection[];
  links_out: string[];
  sources: WikiSource[];
  updated_at: string;
  status: string;
}

export interface WikiIndexEntry {
  slug: string;
  title: string;
  type: string;
  category: string;
  summary: string;
  aliases: string[];
}

interface Graph {
  backlinks: Record<string, string[]>;
}

/** Display name + short blurb for each category slug. */
export const CATEGORY_META: Record<string, { name: string; blurb: string }> = {
  geography: {
    name: "Land & Geography",
    blurb: "Cities, rivers, regions, and the physical landscape of Ukraine.",
  },
  history: {
    name: "History",
    blurb: "From Kyivan Rus' and the Cossacks to independence.",
  },
  war: {
    name: "Russia–Ukraine War",
    blurb: "The invasion, key battles, and the conflict since 2014.",
  },
  politics: {
    name: "Government & Politics",
    blurb: "The state, its institutions, leaders, and constitution.",
  },
  people: {
    name: "People & Society",
    blurb: "The Ukrainian people, language, and religious life.",
  },
  culture: {
    name: "Culture & Arts",
    blurb: "Cuisine, music, folk traditions, and national symbols.",
  },
  economy: {
    name: "Economy & Industry",
    blurb: "Agriculture, currency, and the wider Ukrainian economy.",
  },
  other: {
    name: "Other",
    blurb: "Further topics connected to Ukraine.",
  },
};

/** Left-to-right ordering used across the site. */
export const CATEGORY_ORDER = [
  "geography",
  "history",
  "war",
  "politics",
  "people",
  "culture",
  "economy",
  "other",
];

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

const pageModules = import.meta.glob<{ default: WikiPage }>(
  "../data/wiki/pages/*.json",
  { eager: true },
);

const pagesBySlug: Map<string, WikiPage> = (() => {
  const map = new Map<string, WikiPage>();
  for (const mod of Object.values(pageModules)) {
    const page = mod.default;
    map.set(page.slug, page);
  }
  return map;
})();

export const wikiIndex = indexJson as WikiIndexEntry[];
export const redirects = redirectsJson as Record<string, string>;
const graph = graphJson as Graph;

/** GitHub-style slug used for anchors and ids. */
export function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Some entity titles arrive lowercased (e.g. "borscht", "agriculture in
 * Ukraine"). Capitalize the leading character for headings, <title>, and lists
 * without touching intentionally-cased words later in the string.
 */
export function displayTitle(title: string): string {
  if (!title) return title;
  return title.charAt(0).toUpperCase() + title.slice(1);
}

/** Trim a summary to a clean meta-description length at a word boundary. */
export function clampDescription(text: string, max = 155): string {
  const s = stripWikitext(text).replace(/\s+/g, " ").trim();
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 40 ? lastSpace : max).trimEnd()}…`;
}

/**
 * Map a request pathname to the key of its generated OG image (see
 * `src/pages/og/[...route].png.ts`). Falls back to the home image for routes
 * without a dedicated image (search, 404, alias redirects).
 */
export function ogKeyForPath(pathname: string): string {
  const clean = pathname.replace(/^\/+|\/+$/g, "");
  if (clean === "") return "index";
  if (clean === "wiki/a-z") return "wiki/a-z";
  const cat = clean.match(/^wiki\/category\/([a-z0-9-]+)$/);
  if (cat && getCategory(cat[1])) return clean;
  const slug = clean.match(/^wiki\/([a-z0-9-]+)$/);
  if (slug && hasPage(slug[1])) return clean;
  return "index";
}

export function getPage(slug: string): WikiPage | undefined {
  return pagesBySlug.get(slug);
}

export function hasPage(slug: string): boolean {
  return pagesBySlug.has(slug);
}

export function allPages(): WikiPage[] {
  return [...pagesBySlug.values()];
}

export function getBacklinks(slug: string): WikiIndexEntry[] {
  const slugs = graph.backlinks[slug] ?? [];
  return slugs
    .map((s) => wikiIndex.find((e) => e.slug === s))
    .filter((e): e is WikiIndexEntry => Boolean(e))
    .sort((a, b) => a.title.localeCompare(b.title));
}

export interface WikiCategory {
  slug: string;
  name: string;
  blurb: string;
  entries: WikiIndexEntry[];
}

export function getCategories(): WikiCategory[] {
  const byCat = new Map<string, WikiIndexEntry[]>();
  for (const entry of wikiIndex) {
    const list = byCat.get(entry.category) ?? [];
    list.push(entry);
    byCat.set(entry.category, list);
  }
  const rank = (slug: string) => {
    const i = CATEGORY_ORDER.indexOf(slug);
    return i === -1 ? CATEGORY_ORDER.length : i;
  };
  return [...byCat.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]))
    .map(([slug, entries]) => ({
      slug,
      name: CATEGORY_META[slug]?.name ?? slug,
      blurb: CATEGORY_META[slug]?.blurb ?? "",
      entries: [...entries].sort((a, b) => a.title.localeCompare(b.title)),
    }));
}

export function getCategory(slug: string): WikiCategory | undefined {
  return getCategories().find((c) => c.slug === slug);
}

export function categoryName(slug: string): string {
  return CATEGORY_META[slug]?.name ?? slug;
}

export const wikiCounts = {
  pages: pagesBySlug.size,
  links: Object.values(graph.backlinks).reduce((n, l) => n + l.length, 0),
  categories: new Set(wikiIndex.map((e) => e.category)).size,
};

// ---------------------------------------------------------------------------
// Wikilink parsing:  [[slug|display text]]  ->  tokens
// ---------------------------------------------------------------------------

export type WikiToken =
  | { type: "text"; value: string }
  | { type: "link"; slug: string; text: string; exists: boolean };

const LINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;

export function parseWikitext(text: string): WikiToken[] {
  const tokens: WikiToken[] = [];
  let last = 0;
  for (const m of text.matchAll(LINK_RE)) {
    const start = m.index ?? 0;
    if (start > last) {
      tokens.push({ type: "text", value: text.slice(last, start) });
    }
    const slug = m[1].trim();
    const display = (m[2] ?? m[1]).trim();
    tokens.push({
      type: "link",
      slug,
      text: display,
      exists: hasPage(slug),
    });
    last = start + m[0].length;
  }
  if (last < text.length) {
    tokens.push({ type: "text", value: text.slice(last) });
  }
  return tokens;
}

/** Remove wikilink markup, keeping the display text — for plain contexts. */
export function stripWikitext(text: string): string {
  return text.replace(LINK_RE, (_all, slug, display) =>
    (display ?? slug).trim(),
  );
}
