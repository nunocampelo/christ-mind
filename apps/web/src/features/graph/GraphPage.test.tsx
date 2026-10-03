import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ArtifactError, type GraphArtifact } from "@/api/graphArtifact";
import GraphPage from "@/features/graph/GraphPage";
import { makeArtifact } from "@/features/graph/fixture";

// Cytoscape needs a real canvas; jsdom has none. The page's view behavior (navigation,
// selection, counts, evidence) lives outside the canvas, so stub it to a plain div that
// still exposes edge selection — the plan requires testing view behavior independently of
// canvas pixel coordinates.
vi.mock("@/features/graph/GraphCanvas", () => ({
  default: ({ onSelectEdge }: { onSelectEdge: (claimId: string) => void }) => (
    <div data-testid="graph-canvas-stub" onClick={() => onSelectEdge("c_causes")} />
  ),
}));

const loadOf = (artifact: GraphArtifact) => () => Promise.resolve(artifact);
const failWith = (e: unknown) => () => Promise.reject(e);

const renderGraph = (load: Parameters<typeof GraphPage>[0]["load"]) =>
  render(<GraphPage load={load} />);

const start = async (user: ReturnType<typeof userEvent.setup>, label = "forgiveness") => {
  const button = await screen.findByRole("button", { name: label });
  await user.click(button);
};

describe("GraphPage load states", () => {
  it("shows the error state when the artifact fails to load", async () => {
    renderGraph(failWith(new ArtifactError("incompatible schema 0.0.0")));
    expect(await screen.findByTestId("graph-error")).toBeInTheDocument();
    expect(screen.getByTestId("graph-error")).toHaveTextContent("incompatible schema");
  });

  it("shows the no-selection prompt once the artifact is ready", async () => {
    renderGraph(loadOf(makeArtifact()));
    expect(await screen.findByTestId("graph-no-selection")).toBeInTheDocument();
    expect(screen.getByTestId("starting-points")).toBeInTheDocument();
  });
});

describe("GraphPage exploration", () => {
  it("picks a starting point and lists its relationships", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    const edges = await screen.findAllByTestId("rel-edge");
    // forgiveness: c_causes, c_causes_neg, c_incoming, c_self (self-loop deduped)
    expect(edges).toHaveLength(4);
    expect(screen.getByTestId("nonprojectable-list")).toHaveTextContent("forgiveness makes");
  });

  it("selects an edge from the list, rendering evidence, qualifiers, and highlight", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    // the negated parallel edge: polarity must survive into the gloss and a qualifier chip
    const negated = (await screen.findAllByTestId("rel-edge")).find((b) =>
      b.textContent?.includes("undoes fear in"),
    )!;
    await user.click(negated);

    const panel = screen.getByTestId("evidence-panel");
    expect(panel).toHaveTextContent("Not: forgiveness undoes fear in healing");
    expect(screen.getByTestId("qualifiers")).toHaveTextContent("Negated");
    expect(screen.getByTestId("evidence-clause")).toHaveTextContent("forgiveness undoes fear");
    // highlight: the clause is wrapped in <mark> inside the context blockquote
    const context = screen.getByTestId("evidence-context");
    expect(context.querySelector("mark")?.textContent).toBe("forgiveness undoes fear");
    // non-BMP context survives verbatim (never re-sliced on offsets)
    expect(context).toHaveTextContent("👁");
    expect(negated).toHaveAttribute("data-active", "true");
  });

  it("selects a non-projectable claim and names its exclusion reason", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("rel-nonprojectable"));
    expect(screen.getByTestId("exclusion-reason")).toHaveTextContent("missing object");
  });

  it("selects an edge from the canvas stub", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("graph-canvas-stub"));
    expect(screen.getByTestId("evidence-panel")).toHaveTextContent("forgiveness brings about healing");
  });
});

describe("GraphPage navigation", () => {
  it("filters by direction and reflects it in the counts", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("direction-outgoing"));
    // outgoing from forgiveness: c_causes, c_causes_neg, c_self → 3 edges
    await waitFor(() => expect(screen.getAllByTestId("rel-edge")).toHaveLength(3));
    expect(screen.getByTestId("counts")).toHaveTextContent("3 of 3 filtered");
    expect(screen.getByTestId("counts")).toHaveTextContent("4 total eligible");
  });

  it("expands to a neighbor, then Previous restores the prior center", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);
    await screen.findAllByTestId("rel-edge");

    // expand into healing
    const toHealing = screen
      .getAllByTestId("expand-neighbor")
      .find((b) => b.textContent?.includes("healing"))!;
    await user.click(toHealing);

    // healing's only relationships are the two forgiveness→healing edges (now incoming)
    await waitFor(() =>
      expect(screen.getByTestId("relationship-list")).toHaveTextContent("brings about"),
    );

    await user.click(screen.getByTestId("back"));
    // back on forgiveness: its 4 edges again
    await waitFor(() => expect(screen.getAllByTestId("rel-edge")).toHaveLength(4));
  });

  it("resets filters without changing the center", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);
    await screen.findAllByTestId("rel-edge");

    await user.click(screen.getByTestId("direction-incoming"));
    await waitFor(() => expect(screen.getAllByTestId("rel-edge")).toHaveLength(2));

    await user.click(screen.getByTestId("reset"));
    await waitFor(() => expect(screen.getAllByTestId("rel-edge")).toHaveLength(4));
  });

  it("searches, keeps ambiguous matches distinct, and lands on a pick", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await screen.findByTestId("graph-no-selection");

    await user.type(screen.getByTestId("search-input"), "forgive");
    const results = await screen.findAllByTestId("search-result");
    expect(results).toHaveLength(1); // forgiveness node only
    await user.click(results[0]);
    expect(await screen.findByTestId("relationship-list")).toBeInTheDocument();
  });

  it("tells the user when a concept has no match", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await screen.findByTestId("graph-no-selection");

    await user.type(screen.getByTestId("search-input"), "zzzznope");
    expect(await screen.findByTestId("search-empty")).toHaveTextContent("No concept matches");
  });
});
