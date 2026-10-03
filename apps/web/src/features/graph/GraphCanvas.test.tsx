import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GraphCanvas from "@/features/graph/GraphCanvas";
import { buildIndex, neighborhood, defaultFilters } from "@/features/graph/graphModel";
import { F, makeArtifact } from "@/features/graph/fixture";

// The tap handler is registered once at mount, but the callback that resolves an edge id
// against the CURRENT neighborhood changes as the user explores. This test captures the
// registered handler and fires it after the callback prop changes, asserting the latest
// callback runs — not the one captured on the first render. It fails against a mount-only
// binding that closes over the initial callback.

type TapHandler = (evt: { target: { id: () => string } }) => void;
let tapHandler: TapHandler | null = null;

const fakeCy = () => {
  const chainableNoop = () => api;
  const api: Record<string, unknown> = {
    on: (_event: string, _selector: string, handler: TapHandler) => {
      tapHandler = handler;
      return api;
    },
    style: chainableNoop,
    elements: () => ({ remove: () => {} }),
    add: () => {},
    layout: () => ({ run: () => {} }),
    fit: () => {},
    zoom: () => 1,
    center: () => {},
    edges: () => ({ removeClass: () => api }),
    nodes: () => ({ removeClass: () => api }),
    getElementById: () => ({ addClass: () => {} }),
    destroy: () => {},
  };
  return api;
};

vi.mock("cytoscape", () => ({ default: () => fakeCy() }));

const index = buildIndex(makeArtifact());
const view = neighborhood(index, F.node_id, defaultFilters())!;

const renderCanvas = (onSelectEdge: (id: string) => void) =>
  render(
    <GraphCanvas
      neighborhood={view}
      index={index}
      selection={null}
      onSelectEdge={onSelectEdge}
    />,
  );

describe("GraphCanvas tap handler", () => {
  beforeEach(() => {
    tapHandler = null;
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("routes a tap to the current callback after the prop changes", () => {
    const first = vi.fn();
    const second = vi.fn();

    const { rerender } = renderCanvas(first);
    expect(tapHandler).not.toBeNull();

    rerender(
      <GraphCanvas
        neighborhood={view}
        index={index}
        selection={null}
        onSelectEdge={second}
      />,
    );

    tapHandler!({ target: { id: () => "c_incoming" } });

    expect(second).toHaveBeenCalledWith("c_incoming");
    expect(first).not.toHaveBeenCalled();
  });
});
