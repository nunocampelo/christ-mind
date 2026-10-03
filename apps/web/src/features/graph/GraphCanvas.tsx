import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { type GraphIndex, type Neighborhood } from "@/features/graph/graphModel";
import type { Selection } from "@/features/graph/EvidencePanel";

// The Cytoscape canvas. Deliberately thin: it renders the current neighborhood and reports
// edge selection back up. It does NOT own neighborhood/filter state — that lives in the page
// so the relationship list and canvas stay in sync. Parallel edges and self-loops are kept
// distinct (one graph edge per claim; curve-style bezier so parallels don't overlap).

// Cytoscape paints to a <canvas> and parses colors with its OWN parser — it understands
// rgb()/hex/named colors, NOT the oklch() our design tokens use. Rather than resolve tokens
// at runtime (fragile against the canvas parser), we hand Cytoscape a fixed hex palette, one
// per theme, picked to read well on both. The theme is detected from the .dark class on
// <html> and the palette is re-applied when it flips.
interface Palette {
  foreground: string;
  mutedForeground: string;
  muted: string;
  border: string;
  primary: string;
  primaryForeground: string;
  background: string;
}

const LIGHT: Palette = {
  foreground: "#2a2740",
  mutedForeground: "#6b6880",
  muted: "#eceaf6",
  border: "#d6d2e8",
  primary: "#5b4fc4",
  primaryForeground: "#ffffff",
  background: "#ffffff",
};

const DARK: Palette = {
  foreground: "#e9e6f5",
  mutedForeground: "#a39fbd",
  muted: "#2b2a3d",
  border: "#413e58",
  primary: "#9b8cf0",
  primaryForeground: "#1a1826",
  background: "#201e2e",
};

const currentPalette = (): Palette =>
  document.documentElement.classList.contains("dark") ? DARK : LIGHT;

const stylesheetFor = (t: Palette): cytoscape.StylesheetJson => [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": "12px",
      "font-family": "inherit",
      "text-wrap": "wrap",
      "text-max-width": "130px",
      "background-color": t.muted,
      "border-width": 1,
      "border-color": t.border,
      color: t.foreground,
      "text-valign": "center",
      "text-halign": "center",
      width: "label",
      height: "label",
      padding: "12px",
      shape: "round-rectangle",
      "transition-property": "background-color, border-color, border-width",
      "transition-duration": 120,
    },
  },
  {
    selector: "node.center",
    style: {
      "background-color": t.primary,
      "border-color": t.primary,
      color: t.primaryForeground,
      "font-weight": "bold",
      "z-index": 10,
    },
  },
  {
    selector: "edge",
    style: {
      label: "data(label)",
      "font-size": "10px",
      "font-family": "inherit",
      color: t.mutedForeground,
      "curve-style": "bezier",
      "control-point-step-size": 48,
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.9,
      "line-color": t.border,
      "target-arrow-color": t.border,
      width: 1.5,
      "text-rotation": "autorotate",
      "text-background-color": t.background,
      "text-background-opacity": 0.9,
      "text-background-padding": "3px",
      "text-background-shape": "roundrectangle",
    },
  },
  {
    selector: "edge.negated",
    style: {
      "line-style": "dashed",
      "line-color": t.mutedForeground,
      "target-arrow-color": t.mutedForeground,
    },
  },
  {
    selector: "edge.selected",
    style: {
      "line-color": t.primary,
      "target-arrow-color": t.primary,
      color: t.foreground,
      width: 2.5,
      "z-index": 20,
    },
  },
  {
    selector: "node.center.selected-end",
    style: { "border-width": 2, "border-color": t.primary },
  },
];

const elementsFor = (nb: Neighborhood, index: GraphIndex): ElementDefinition[] => {
  const centerId = nb.center.node_id;
  const nodeIds = new Set<string>([centerId, ...nb.neighbors.map((n) => n.node_id)]);
  const nodes: ElementDefinition[] = [...nodeIds].map((id) => {
    const node = index.nodeById.get(id);
    return {
      data: { id, label: node?.label ?? id },
      classes: id === centerId ? "center" : "",
    };
  });
  const edges: ElementDefinition[] = nb.edges.map((e) => ({
    data: {
      id: e.claim_id,
      source: e.source_node_id,
      target: e.target_node_id,
      label: e.verb_phrase,
    },
    classes: e.polarity === "negated" ? "negated" : "",
  }));
  return [...nodes, ...edges];
};

const LAYOUT = {
  name: "concentric",
  animate: false,
  padding: 36,
  minNodeSpacing: 70,
  concentric: (n: cytoscape.NodeSingular) => (n.hasClass("center") ? 2 : 1),
  levelWidth: () => 1,
} as const;

const GraphCanvas = ({
  neighborhood,
  index,
  selection,
  onSelectEdge,
}: {
  neighborhood: Neighborhood;
  index: GraphIndex;
  selection: Selection | null;
  onSelectEdge: (claimId: string) => void;
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  // The tap handler is bound once at mount, but the neighborhood (and the callback that
  // resolves an edge id against it) changes as the user explores. Route taps through a ref
  // so the mount-time handler always calls the current callback, not the one captured on
  // the first render.
  const onSelectEdgeRef = useRef(onSelectEdge);
  useEffect(() => {
    onSelectEdgeRef.current = onSelectEdge;
  });

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      style: stylesheetFor(currentPalette()),
      elements: [],
      minZoom: 0.3,
      maxZoom: 2.5,
      // layout runs per content update below, not on every re-render
    });
    cy.on("tap", "edge", (evt) => onSelectEdgeRef.current(evt.target.id()));
    cyRef.current = cy;

    // Recolor live when the theme flips (.dark toggles on <html>).
    const observer = new MutationObserver(() => {
      cy.style(stylesheetFor(currentPalette()));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => {
      observer.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
    // Mount once; element/selection sync happens in the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-seed elements when the neighborhood changes (new center or filters), then run a
  // single layout over the current content rather than animating the whole canvas.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().remove();
    cy.add(elementsFor(neighborhood, index));
    cy.layout(LAYOUT).run();
    cy.fit(undefined, 48);
    // fit() zooms a sparse neighborhood all the way to maxZoom, blowing the pills up to
    // fill the canvas. Cap it so a 2–3 node graph stays at a readable scale, re-centered.
    if (cy.zoom() > 1.1) {
      cy.zoom(1.1);
      cy.center();
    }
  }, [neighborhood, index]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().removeClass("selected");
    cy.nodes().removeClass("selected-end");
    if (selection?.kind === "edge") {
      cy.getElementById(selection.edge.claim_id).addClass("selected");
    }
  }, [selection]);

  return <div ref={containerRef} className="graph-canvas" data-testid="graph-canvas" />;
};

export default GraphCanvas;
