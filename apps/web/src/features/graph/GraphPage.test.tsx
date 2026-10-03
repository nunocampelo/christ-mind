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

  it("reads the full passage with the clause highlighted, no redundant repetition", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    // the negated parallel edge: polarity shows as a qualifier chip
    const negated = (await screen.findAllByTestId("rel-edge")).find((b) =>
      b.textContent?.includes("undoes fear in"),
    )!;
    // the suffix is visible in the list itself, before selection
    expect(negated).toHaveTextContent("· Negated");
    await user.click(negated);

    expect(screen.getByTestId("qualifiers")).toHaveTextContent("Negated");

    // the whole passage is visible at once, with the supporting clause marked in place
    const passage = screen.getByTestId("passage");
    expect(passage).toHaveTextContent("forgiveness undoes fear entirely.");
    expect(screen.getByTestId("passage-clause").textContent).toBe("forgiveness undoes fear");
    expect(passage.querySelector("mark")).not.toBeNull();
    // non-BMP context survives verbatim (never re-sliced on offsets)
    expect(passage).toHaveTextContent("👁");

    // the old redundancy is gone: no gloss sentence, no standalone clause quote, no
    // collapsed "Show in context"
    expect(screen.queryByTestId("evidence-clause")).toBeNull();
    expect(screen.queryByTestId("evidence-context")).toBeNull();
    const panel = screen.getByTestId("evidence-panel");
    expect(panel).not.toHaveTextContent("Not: forgiveness undoes fear in healing");

    expect(negated).toHaveAttribute("data-active", "true");
  });

  it("shows no qualifier suffix on a plain Course assertion", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    // c_causes: affirmed / assertion / course → no suffix
    const plain = (await screen.findAllByTestId("rel-edge")).find((b) =>
      b.textContent?.includes("brings about"),
    )!;
    expect(plain.textContent).not.toContain("·");
  });

  it("shows a compact ACIM reference with an inline caveat and source-only details", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("rel-nonprojectable"));
    const ref = screen.getByTestId("source-reference");
    expect(ref).toHaveTextContent("A Course in Miracles · Ch 1 · Sec 1 · Block 1");
    expect(ref).toHaveTextContent("(stored location, not a verified citation)");

    const details = screen.getByTestId("source-details");
    expect(details).toHaveTextContent("Dataset edition: “Sparkly Edition”");
    expect(details).toHaveTextContent("ID: s6");
    // "Source details" is about the SOURCE only — never why the claim isn't drawn
    expect(details).not.toHaveTextContent("missing object");
    expect(details).not.toHaveTextContent("Not shown in graph");
  });

  it("names the exclusion reason above the passage, not in source details", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("rel-nonprojectable"));
    expect(screen.getByTestId("exclusion-reason")).toHaveTextContent(
      "Not shown in graph: missing object",
    );
  });

  it("selects an edge from the canvas stub", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await start(user);

    await user.click(await screen.findByTestId("graph-canvas-stub"));
    expect(screen.getByTestId("evidence-panel")).toHaveTextContent("forgiveness brings about healing");
  });

  it("reaches a concept that appears only in a non-projectable claim", async () => {
    const user = userEvent.setup();
    renderGraph(loadOf(makeArtifact()));
    await screen.findByTestId("graph-no-selection");

    // atonement has a node but no drawable edge — searchable and selectable.
    await user.type(screen.getByTestId("search-input"), "atonement");
    const results = await screen.findAllByTestId("search-result");
    expect(results).toHaveLength(1);
    await user.click(results[0]);

    // no drawable relationships, but its claim is listed and inspectable
    expect(await screen.findByTestId("graph-no-relationships")).toBeInTheDocument();
    await user.click(await screen.findByTestId("rel-nonprojectable"));
    const panel = screen.getByTestId("evidence-panel");
    expect(panel).toHaveTextContent("atonement");
    expect(screen.getByTestId("passage-clause")).toHaveTextContent("atonement");
    // qualifiers survive on a non-projectable claim too
    expect(screen.getByTestId("qualifiers")).toHaveTextContent("Conditional");
    expect(screen.getByTestId("qualifiers")).toHaveTextContent("Attributed to ego");
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
