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

function initRoot(root: HTMLElement) {
  if (root.dataset.kgReady === "1") return;

  const jsonEl = root.querySelector<HTMLElement>("[data-kg-json]");
  const mount = root.querySelector<HTMLElement>("[data-kg-mount]");
  const hint = root.querySelector<HTMLElement>("[data-kg-hint]");
  const filterInput = root.querySelector<HTMLInputElement>("[data-kg-filter]");
  if (!jsonEl || !mount) return;
  const host = mount;

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

  const compact = Boolean(payload.compact);
  const focusId = payload.focus;

  // force-graph types nodes as NodeObject; cast accessors lightly.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Graph = new ForceGraph(host) as any;

  Graph.graphData({ nodes, links })
    .backgroundColor(cssVar("--color-canvas-soft", "#dddddf"))
    .nodeId("id")
    .nodeLabel((n: GNode) => n.title)
    .nodeVal((n: GNode) => 1 + Math.min(n.degree, 28) * 0.4)
    .nodeRelSize(compact ? 4.5 : 3.4)
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
    .linkWidth((l: GLink) => (highlightLinks.has(l) ? 2 : 0.55))
    .linkDirectionalParticles((l: GLink) => (highlightLinks.has(l) ? 2 : 0))
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleSpeed(0.005)
    .autoPauseRedraw(false)
    .enableNodeDrag(true)
    .cooldownTicks(160)
    .d3AlphaDecay(0.02)
    .d3VelocityDecay(0.28)
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
          (!compact && !filter && n.degree >= 14 && globalScale > 1.2);
        if (!show) return;
        if (filter && !matchFilter && n.id !== hoverId) return;

        const fontSize = Math.max(11 / globalScale, 2.6);
        ctx.font = `${fontSize}px system-ui, -apple-system, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = cssVar("--color-mute", "#85888e");
        const r =
          Math.sqrt(1 + Math.min(n.degree, 28) * 0.4) *
          (compact ? 4.5 : 3.4) *
          0.55;
        ctx.fillText(n.title, n.x ?? 0, (n.y ?? 0) + r + 1.5);
      },
    )
    .onEngineStop(() => {
      if (fitted) return;
      fitted = true;
      if (focusId && byId.has(focusId)) {
        const focus = byId.get(focusId)!;
        Graph.centerAt(focus.x ?? 0, focus.y ?? 0, 600);
        Graph.zoom(compact ? 2.6 : 2.1, 600);
      } else {
        Graph.zoomToFit(700, 56);
      }
    });

  const charge = Graph.d3Force("charge");
  if (charge?.strength) charge.strength(compact ? -70 : -50);

  const linkForce = Graph.d3Force("link");
  if (linkForce?.distance) linkForce.distance(compact ? 38 : 48);

  function resize() {
    const parent = host.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    Graph.width(Math.max(1, rect.width)).height(Math.max(1, rect.height));
  }

  new ResizeObserver(() => resize()).observe(host.parentElement!);
  resize();

  filterInput?.addEventListener("input", () => {
    filter = filterInput.value.trim().toLowerCase();
    highlightIds.clear();
    highlightLinks.clear();
    if (filter) {
      const match = nodes.find((n) => n.title.toLowerCase().includes(filter));
      if (match) {
        Graph.centerAt(match.x ?? 0, match.y ?? 0, 700);
        Graph.zoom(2.6, 700);
        highlightIds.add(match.id);
        neighbors.get(match.id)?.forEach((id) => highlightIds.add(id));
        incident.get(match.id)?.forEach((l) => highlightLinks.add(l));
        if (hint) hint.textContent = match.title;
      }
    } else if (hint) {
      hint.textContent = "";
    }
    Graph.nodeColor(Graph.nodeColor());
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
