import ForceGraph from "force-graph";

type GNode = {
  id: string;
  title: string;
  category: string;
  degree: number;
  x?: number;
  y?: number;
};

type GLink = {
  source: string | GNode;
  target: string | GNode;
};

type Payload = {
  nodes: { id: string; title: string; category: string; degree: number }[];
  edges: { source: string; target: string }[];
  focus: string | null;
  compact: boolean;
};

const COLORS: Record<string, [string, string]> = {
  geography: ["#6b7f9a", "#8fa3bc"],
  history: ["#8a7360", "#b39a84"],
  war: ["#8f5e5a", "#b88884"],
  politics: ["#6f6b8a", "#9a96b4"],
  people: ["#5f7a72", "#88a49c"],
  culture: ["#8a7a52", "#b4a474"],
  economy: ["#5f7a5f", "#88a488"],
  other: ["#7a7a7a", "#9a9a9a"],
};

function isDark() {
  const root = document.documentElement;
  if (root.classList.contains("dark")) return true;
  if (root.classList.contains("light")) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function cssVar(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return v || fallback;
}

function catColor(category: string) {
  const pair = COLORS[category] ?? COLORS.other;
  return isDark() ? pair[1] : pair[0];
}

function endId(end: string | GNode) {
  return typeof end === "object" ? end.id : end;
}

function isNarrow() {
  return window.matchMedia("(max-width: 1023px)").matches;
}

function initRoot(root: HTMLElement) {
  if (root.dataset.kgReady === "1") return;

  const jsonEl = root.querySelector<HTMLElement>("[data-kg-json]");
  const mount = root.querySelector<HTMLElement>("[data-kg-mount]");
  const viewport = root.querySelector<HTMLElement>("[data-kg-viewport]");
  const hint = root.querySelector<HTMLElement>("[data-kg-hint]");
  const filterInput = root.querySelector<HTMLInputElement>("[data-kg-filter]");
  if (!jsonEl || !mount || !viewport) return;
  const host = mount;
  const frame = viewport;

  let payload: Payload;
  try {
    payload = JSON.parse(jsonEl.textContent || "{}") as Payload;
  } catch {
    return;
  }

  root.dataset.kgReady = "1";

  const nodes: GNode[] = payload.nodes.map((n) => ({ ...n }));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links: GLink[] = payload.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  const neighbors = new Map<string, Set<string>>();
  const incident = new Map<string, GLink[]>();
  for (const n of nodes) {
    neighbors.set(n.id, new Set());
    incident.set(n.id, []);
  }
  for (const link of links) {
    const s = endId(link.source);
    const t = endId(link.target);
    neighbors.get(s)?.add(t);
    neighbors.get(t)?.add(s);
    incident.get(s)?.push(link);
    incident.get(t)?.push(link);
  }

  const highlightIds = new Set<string>();
  const highlightLinks = new Set<GLink>();
  let hoverId: string | null = null;
  let filter = "";
  let fitted = false;
  let engineDone = false;

  const compact = Boolean(payload.compact);
  const focusId = payload.focus;
  const narrow = isNarrow();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Graph = new ForceGraph(host) as any;

  Graph.graphData({ nodes, links })
    .backgroundColor(cssVar("--color-canvas-soft", "#dddddf"))
    .nodeId("id")
    .nodeLabel((n: GNode) => n.title)
    .nodeVal((n: GNode) => 1 + Math.min(n.degree, 28) * 0.45)
    .nodeRelSize(compact ? 5 : narrow ? 5.5 : 3.6)
    .nodeColor((n: GNode) => {
      if (filter && !n.title.toLowerCase().includes(filter)) {
        return isDark() ? "#2a2a27" : "#cbcbcd";
      }
      if (highlightIds.size && !highlightIds.has(n.id)) {
        return isDark() ? "#3a3a36" : "#b8b8ba";
      }
      return catColor(n.category);
    })
    .linkColor((l: GLink) =>
      highlightLinks.has(l)
        ? cssVar("--color-body", "#545860")
        : cssVar("--color-hairline", "#cbcbcd"),
    )
    .linkWidth((l: GLink) => (highlightLinks.has(l) ? 2.2 : narrow ? 0.7 : 0.55))
    .linkDirectionalParticles((l: GLink) => (highlightLinks.has(l) ? 2 : 0))
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleSpeed(0.005)
    .autoPauseRedraw(false)
    .enableNodeDrag(true)
    .cooldownTicks(140)
    .d3AlphaDecay(0.025)
    .d3VelocityDecay(0.3)
    .onNodeHover((n: GNode | null) => {
      hoverId = n?.id ?? null;
      highlightIds.clear();
      highlightLinks.clear();
      if (n) {
        highlightIds.add(n.id);
        neighbors.get(n.id)?.forEach((id) => highlightIds.add(id));
        incident.get(n.id)?.forEach((l) => highlightLinks.add(l));
      }
      if (hint) hint.textContent = n ? n.title : "";
      host.style.cursor = n ? "pointer" : "grab";
    })
    .onNodeClick((n: GNode) => {
      window.location.href = `/wiki/${n.id}/`;
    })
    .nodeCanvasObjectMode(() => "after")
    .nodeCanvasObject(
      (n: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const matchFilter = Boolean(
          filter && n.title.toLowerCase().includes(filter),
        );
        const show =
          n.id === hoverId ||
          n.id === focusId ||
          matchFilter ||
          (compact && nodes.length <= 36) ||
          (narrow && n.degree >= 10 && globalScale > 0.9) ||
          (!compact && !narrow && !filter && n.degree >= 14 && globalScale > 1.2);
        if (!show) return;
        if (filter && !matchFilter && n.id !== hoverId) return;

        const fontSize = Math.max((narrow ? 12 : 11) / globalScale, 2.8);
        ctx.font = `${fontSize}px system-ui, -apple-system, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = cssVar("--color-mute", "#85888e");
        const r =
          Math.sqrt(1 + Math.min(n.degree, 28) * 0.45) *
          (compact ? 5 : narrow ? 5.5 : 3.6) *
          0.55;
        ctx.fillText(n.title, n.x ?? 0, (n.y ?? 0) + r + 1.5);
      },
    )
    .onEngineStop(() => {
      engineDone = true;
      fitIfReady();
    });

  const charge = Graph.d3Force("charge");
  if (charge?.strength) charge.strength(compact ? -70 : narrow ? -90 : -50);

  const linkForce = Graph.d3Force("link");
  if (linkForce?.distance) linkForce.distance(compact ? 38 : narrow ? 34 : 48);

  function fitIfReady() {
    if (fitted || !engineDone) return;
    const rect = frame.getBoundingClientRect();
    if (rect.width < 80 || rect.height < 80) return;
    fitted = true;
    if (focusId && byId.has(focusId)) {
      const focus = byId.get(focusId)!;
      Graph.centerAt(focus.x ?? 0, focus.y ?? 0, 500);
      Graph.zoom(compact ? 2.6 : narrow ? 1.6 : 2.1, 500);
    } else {
      // Tight padding on phones so nodes stay large enough to see.
      Graph.zoomToFit(600, narrow ? 24 : 48);
    }
  }

  function resize() {
    const rect = frame.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    // Keep the mount box explicit — percentage heights are flaky on mobile.
    host.style.width = `${w}px`;
    host.style.height = `${h}px`;
    Graph.width(w).height(h);
    // If we couldn't fit earlier because the viewport was 0×0, try again.
    if (!fitted && engineDone && w >= 80 && h >= 80) {
      fitIfReady();
    }
  }

  new ResizeObserver(() => resize()).observe(frame);
  // Two frames: wait for layout (esp. mobile browser chrome) then size.
  requestAnimationFrame(() => {
    resize();
    requestAnimationFrame(resize);
  });
  // Fallback if the first layouts still report a tiny box.
  window.setTimeout(resize, 250);
  window.setTimeout(() => {
    resize();
    if (!fitted && engineDone) fitIfReady();
  }, 700);

  function focusNode(id: string, opts: { clearFilter?: boolean } = {}) {
    const match = byId.get(id);
    if (!match) return;
    if (opts.clearFilter !== false) {
      filter = "";
      if (filterInput) filterInput.value = "";
    }
    highlightIds.clear();
    highlightLinks.clear();
    highlightIds.add(match.id);
    neighbors.get(match.id)?.forEach((nid) => highlightIds.add(nid));
    incident.get(match.id)?.forEach((l) => highlightLinks.add(l));
    Graph.centerAt(match.x ?? 0, match.y ?? 0, 700);
    Graph.zoom(compact ? 2.6 : narrow ? 1.8 : 2.4, 700);
    if (hint) hint.textContent = match.title;
    Graph.nodeColor(Graph.nodeColor());

    root.querySelectorAll<HTMLElement>("[data-kg-goto]").forEach((btn) => {
      const active = btn.dataset.kgGoto === id;
      btn.classList.toggle("bg-canvas-soft", active);
      btn.classList.toggle("font-semibold", active);
    });
  }

  filterInput?.addEventListener("input", () => {
    filter = filterInput.value.trim().toLowerCase();
    highlightIds.clear();
    highlightLinks.clear();
    if (filter) {
      const match = nodes.find((n) => n.title.toLowerCase().includes(filter));
      if (match) focusNode(match.id, { clearFilter: false });
      else Graph.nodeColor(Graph.nodeColor());
    } else if (hint) {
      hint.textContent = "";
      Graph.nodeColor(Graph.nodeColor());
    }
  });

  root.querySelectorAll<HTMLButtonElement>("[data-kg-goto]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.kgGoto;
      if (id) focusNode(id);
    });
  });

  const refreshTheme = () => {
    Graph.backgroundColor(cssVar("--color-canvas-soft", "#dddddf"));
    Graph.nodeColor(Graph.nodeColor());
    Graph.linkColor(Graph.linkColor());
  };
  new MutationObserver(refreshTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
}

export function initKnowledgeGraphs() {
  document.querySelectorAll<HTMLElement>("[data-kg-root]").forEach(initRoot);
}
