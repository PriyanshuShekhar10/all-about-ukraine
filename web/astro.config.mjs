import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import sitemap from "@astrojs/sitemap";
import { readFileSync } from "node:fs";

const SITE = "https://ukraineporn.com";

// Compute alias-redirect URLs so they can be excluded from the sitemap (they are
// noindex meta-refresh stubs that point at their canonical page).
const wikiDir = new URL("./src/data/wiki/", import.meta.url);
const index = JSON.parse(readFileSync(new URL("index.json", wikiDir), "utf-8"));
const redirects = JSON.parse(
  readFileSync(new URL("redirects.json", wikiDir), "utf-8"),
);
const pageSlugs = new Set(index.map((e) => e.slug));
const aliasUrls = new Set(
  Object.keys(redirects)
    .filter((from) => !pageSlugs.has(from) && /^[a-z0-9-]+$/.test(from))
    .map((from) => `${SITE}/wiki/${from}/`),
);

export default defineConfig({
  site: SITE,
  integrations: [
    sitemap({
      filter: (page) =>
        !aliasUrls.has(page) &&
        !page.startsWith(`${SITE}/og/`) &&
        page !== `${SITE}/404/` &&
        page !== `${SITE}/500/` &&
        page !== `${SITE}/wiki/search/`,
      serialize(item) {
        const u = item.url;
        if (u === `${SITE}/`) item.priority = 1.0;
        else if (u.includes("/wiki/category/")) item.priority = 0.6;
        else if (u === `${SITE}/wiki/a-z/`) item.priority = 0.5;
        else if (u.startsWith(`${SITE}/wiki/`)) item.priority = 0.7;
        else item.priority = 0.5;
        item.changefreq = "weekly";
        item.lastmod = new Date().toISOString();
        return item;
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
