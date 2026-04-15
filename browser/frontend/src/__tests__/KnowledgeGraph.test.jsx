import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../components/ConceptGraph", () => ({
  default: function MockConceptGraph({
    data,
    onConceptActivate,
    onConceptOpenInConversations,
  }) {
    return (
      <div data-testid="concept-graph">
        <span data-testid="node-count">{data.nodes.length}</span>
        <span data-testid="edge-count">{data.edges.length}</span>
        <button
          data-testid="trigger-activate"
          onClick={() =>
            onConceptActivate &&
            onConceptActivate({ id: "n1", name: "Docker" })
          }
        >
          activate
        </button>
        <button
          data-testid="trigger-open-in-conv"
          onClick={() =>
            onConceptOpenInConversations && onConceptOpenInConversations("Docker")
          }
        >
          fast-path
        </button>
      </div>
    );
  },
}));

vi.mock("../components/ConceptWikiPane", () => ({
  default: function MockConceptWikiPane({ article, loading, error, onClose }) {
    return (
      <div data-testid="wiki-pane">
        <span data-testid="wiki-loading">{loading ? "loading" : "idle"}</span>
        <span data-testid="wiki-error">{error ? "errored" : "ok"}</span>
        <span data-testid="wiki-title">{article ? article.title : "no-article"}</span>
        <button data-testid="wiki-close" onClick={onClose}>
          close
        </button>
      </div>
    );
  },
}));

vi.mock("../api", () => ({
  fetchDashboardGraph: vi.fn(),
  fetchDashboardGraphStatus: vi.fn(),
  triggerDashboardGraphGenerate: vi.fn(),
  importDashboardGraph: vi.fn(),
  fetchWikiIndex: vi.fn(),
  fetchWikiArticle: vi.fn(),
  resolveWikiSlug: vi.fn(),
}));

import KnowledgeGraph from "../components/KnowledgeGraph";
import {
  fetchDashboardGraph,
  fetchDashboardGraphStatus,
  triggerDashboardGraphGenerate,
  importDashboardGraph,
  fetchWikiIndex,
  fetchWikiArticle,
  resolveWikiSlug,
} from "../api";

beforeEach(() => {
  vi.clearAllMocks();
  fetchWikiIndex.mockResolvedValue({
    title: "Knowledge Graph Index",
    markdown: "# Knowledge Graph Index\n",
    articles: [],
  });
  fetchWikiArticle.mockResolvedValue({
    slug: "Docker",
    title: "Docker",
    markdown: "# Docker\nbody",
  });
  resolveWikiSlug.mockResolvedValue({ slug: "Docker" });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("KnowledgeGraph — initial loading", () => {
  it("shows 'Loading...' initially before first status resolves", () => {
    fetchDashboardGraphStatus.mockReturnValue(new Promise(() => {}));
    render(<KnowledgeGraph provider="claude" />);
    expect(screen.getByText(/^Loading\.\.\./)).toBeInTheDocument();
  });

  it("renders the header with Knowledge Graph title", () => {
    fetchDashboardGraphStatus.mockReturnValue(new Promise(() => {}));
    render(<KnowledgeGraph provider="claude" />);
    expect(screen.getByText("Knowledge Graph")).toBeInTheDocument();
  });
});

describe("KnowledgeGraph — state = ready with data", () => {
  it("fetches graph data and renders ConceptGraph when has_data is true and nodes > 0", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true, status: "ready" });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Concept" }],
      edges: [{ source: "n1", target: "n2" }],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument()
    );
    expect(screen.getByTestId("node-count").textContent).toBe("1");
    expect(screen.getByTestId("edge-count").textContent).toBe("1");
  });

  it("shows Regenerate button when status is ready with data", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Regenerate" })
      ).toBeInTheDocument()
    );
  });

  it("wiki pane is hidden until a concept is activated", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Docker" }],
      edges: [],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("wiki-pane")).not.toBeInTheDocument();
  });

  it("plain concept activation opens the wiki pane (resolveWikiSlug → openSlug)", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Docker" }],
      edges: [],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("trigger-activate"));
    await waitFor(() =>
      expect(screen.getByTestId("wiki-pane")).toBeInTheDocument(),
    );
    expect(resolveWikiSlug).toHaveBeenCalledWith({
      conceptId: "n1",
      conceptName: "Docker",
    });
    expect(fetchWikiArticle).toHaveBeenCalledWith(
      "Docker",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("cmd-click fast-path bubbles to onOpenInConversations prop", async () => {
    const onOpenInConversations = vi.fn();
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Docker" }],
      edges: [],
    });
    render(
      <KnowledgeGraph
        provider="claude"
        onOpenInConversations={onOpenInConversations}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("trigger-open-in-conv"));
    expect(onOpenInConversations).toHaveBeenCalledWith("Docker");
  });

  it("mouseDown on the wiki resize handle calls startDrag('wiki')", async () => {
    const startDrag = vi.fn();
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Docker" }],
      edges: [],
    });
    const { container } = render(
      <KnowledgeGraph
        provider="claude"
        startDrag={startDrag}
        wikiContainerRef={{ current: null }}
        wikiWidth={360}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("trigger-activate"));
    await waitFor(() =>
      expect(screen.getByTestId("wiki-pane")).toBeInTheDocument(),
    );
    const handle = container.querySelector(".resize-handle-wiki");
    expect(handle).not.toBeNull();
    handle.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(startDrag).toHaveBeenCalledWith("wiki");
  });

  it("close button on the wiki pane closes it", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1", name: "Docker" }],
      edges: [],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("trigger-activate"));
    await waitFor(() =>
      expect(screen.getByTestId("wiki-pane")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("wiki-close"));
    await waitFor(() =>
      expect(screen.queryByTestId("wiki-pane")).not.toBeInTheDocument(),
    );
  });
});

describe("KnowledgeGraph — state = none (data empty)", () => {
  it("shows 'Waiting for concept graph extraction' when has_data with zero nodes", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({ nodes: [], edges: [] });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Waiting for concept graph extraction to start/)
      ).toBeInTheDocument()
    );
  });

  it("shows 'Waiting for concept graph extraction' when status is none (no data at all)", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: false, status: "none" });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Waiting for concept graph extraction to start/)
      ).toBeInTheDocument()
    );
  });
});

describe("KnowledgeGraph — state = generating", () => {
  it("shows progress bar with done/total counts when generating", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "generating",
      progress: { done: 5, total: 20, ok: 4, failed: 1, current: "file-a", model: "claude-opus-4-6" },
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Extracting concepts:.*5.*\/.*20.*files/)
      ).toBeInTheDocument()
    );
  });

  it("shows the current file in progress detail", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "generating",
      progress: { done: 1, total: 10, current: "file-xyz", ok: 1, failed: 0 },
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText(/Current:\s*file \/ xyz/)).toBeInTheDocument()
    );
  });

  it("shows ok/failed/model stats in the detail line", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "generating",
      progress: { done: 3, total: 10, ok: 2, failed: 1, model: "claude-opus-4-6" },
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByText(/2 extracted/)).toBeInTheDocument()
    );
    expect(screen.getByText(/1 failed/)).toBeInTheDocument();
    expect(screen.getByText(/model: claude-opus-4-6/)).toBeInTheDocument();
  });

  it("shows 'Starting...' text when generating with no progress data", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "generating",
      progress: null,
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Starting concept graph extraction/)
      ).toBeInTheDocument()
    );
  });

  it("shows 'Starting...' text when progress.total is 0", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "generating",
      progress: { done: 0, total: 0 },
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Starting concept graph extraction/)
      ).toBeInTheDocument()
    );
  });
});

describe("KnowledgeGraph — state = ready (triggers import)", () => {
  it("auto-imports when status='ready' and has_data=false, then re-fetches graph", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "ready",
    });
    importDashboardGraph.mockResolvedValue({ ok: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByTestId("concept-graph")).toBeInTheDocument()
    );
    expect(importDashboardGraph).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Regenerate" })
    ).toBeInTheDocument();
  });

  it("status='ready' + import OK + empty graph sets status='none'", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "ready",
    });
    importDashboardGraph.mockResolvedValue({ ok: true });
    fetchDashboardGraph.mockResolvedValue({ nodes: [], edges: [] });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Waiting for concept graph extraction/)
      ).toBeInTheDocument()
    );
  });

  it("ignores late status resolution after unmount", async () => {
    let resolveStatus;
    fetchDashboardGraphStatus.mockReturnValue(
      new Promise((res) => { resolveStatus = res; })
    );
    const { unmount } = render(<KnowledgeGraph provider="claude" />);
    unmount();
    resolveStatus({ has_data: false, status: "none" });
    await new Promise((r) => setTimeout(r, 10));
  });

  it("shows 'Importing graph into database...' while import is pending", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "ready",
    });
    let resolveImport;
    importDashboardGraph.mockReturnValue(
      new Promise((res) => {
        resolveImport = res;
      })
    );
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Importing graph into database/)
      ).toBeInTheDocument()
    );
    resolveImport({ ok: false });
  });

  it("sets status=error when importDashboardGraph returns ok=false", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "ready",
    });
    importDashboardGraph.mockResolvedValue({ ok: false });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Graph generation failed/)
      ).toBeInTheDocument()
    );
  });

  it("sets status=error when importDashboardGraph throws", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "ready",
    });
    importDashboardGraph.mockRejectedValue(new Error("boom"));
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Graph generation failed/)
      ).toBeInTheDocument()
    );
  });
});

describe("KnowledgeGraph — state = error", () => {
  it("shows error message + Retry button when status=error", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "error",
    });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Graph generation failed/)
      ).toBeInTheDocument()
    );
    expect(
      screen.getByRole("button", { name: "Retry" })
    ).toBeInTheDocument();
  });

  it("sets status=error when fetchDashboardGraphStatus throws", async () => {
    fetchDashboardGraphStatus.mockRejectedValue(new Error("network"));
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByText(/Graph generation failed/)
      ).toBeInTheDocument()
    );
  });
});

describe("KnowledgeGraph — regenerate button", () => {
  it("Regenerate button calls triggerDashboardGraphGenerate and switches to generating state", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    triggerDashboardGraphGenerate.mockResolvedValue({ status: "generating" });
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Regenerate" })
      ).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(triggerDashboardGraphGenerate).toHaveBeenCalled();
    expect(
      screen.getByText(/Starting concept graph extraction/)
    ).toBeInTheDocument();
  });

  it("sets status=error when triggerDashboardGraphGenerate throws", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({
      has_data: false,
      status: "error",
    });
    triggerDashboardGraphGenerate.mockRejectedValue(new Error("boom"));
    render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument()
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(
        screen.getByText(/Graph generation failed/)
      ).toBeInTheDocument()
    );
  });
});

describe("KnowledgeGraph — provider changes", () => {
  it("re-fetches graph data when provider prop changes", async () => {
    fetchDashboardGraphStatus.mockResolvedValue({ has_data: true });
    fetchDashboardGraph.mockResolvedValue({
      nodes: [{ id: "n1" }],
      edges: [],
    });
    const { rerender } = render(<KnowledgeGraph provider="claude" />);
    await waitFor(() =>
      expect(fetchDashboardGraph).toHaveBeenCalledWith({ provider: "claude" })
    );
    rerender(<KnowledgeGraph provider="codex" />);
    await waitFor(() =>
      expect(fetchDashboardGraph).toHaveBeenCalledWith({ provider: "codex" })
    );
  });
});
