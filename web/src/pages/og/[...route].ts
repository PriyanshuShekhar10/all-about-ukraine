import { OGImageRoute } from "astro-og-canvas";
import { wikiIndex, getCategories, displayTitle } from "@/lib/wiki";

const TAGLINE = "No fantasies. Just centuries of Ukraine’s story, uncensored.";

// One entry per real, indexable route. Keys match `ogKeyForPath` in wiki.ts;
// astro-og-canvas appends the `.png` extension to each key.
const pages: Record<string, { title: string; description: string }> = {
  index: { title: "An Encyclopedia of Ukraine", description: TAGLINE },
  "wiki/a-z": { title: "A–Z Index", description: TAGLINE },
};
for (const c of getCategories()) {
  pages[`wiki/category/${c.slug}`] = { title: c.name, description: TAGLINE };
}
for (const e of wikiIndex) {
  pages[`wiki/${e.slug}`] = { title: displayTitle(e.title), description: TAGLINE };
}

export const { getStaticPaths, GET } = await OGImageRoute({
  pages,
  getImageOptions: (_path, page) => ({
    title: page.title,
    description: page.description,
    bgGradient: [[251, 250, 247]],
    border: { color: [0, 87, 183], width: 18, side: "block-end" },
    padding: 80,
    font: {
      title: { color: [38, 40, 43], size: 72 },
      description: { color: [120, 123, 127], size: 34 },
    },
  }),
});
