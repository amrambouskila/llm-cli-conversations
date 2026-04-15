import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptWikiPane from "../components/ConceptWikiPane";

const sampleArticle = {
  slug: "Docker_Concept",
  title: "Docker Concept",
  markdown: "# Docker Concept\n\nSee [[Other_Topic]] for more details.\n",
};

function defaultProps(overrides = {}) {
  return {
    article: sampleArticle,
    loading: false,
    error: null,
    breadcrumb: [],
    onSlugClick: vi.fn(),
    onJumpToBreadcrumb: vi.fn(),
    onOpenInConversations: vi.fn(),
    onClose: vi.fn(),
    onRegenerate: vi.fn(),
    ...overrides,
  };
}

describe("ConceptWikiPane — loading state", () => {
  it("renders the loading placeholder when loading=true", () => {
    render(<ConceptWikiPane {...defaultProps({ loading: true, article: null })} />);
    // Title shows just "Loading…"; body shows "Loading article…" — use selectors
    // to disambiguate (both contain the literal "Loading").
    expect(
      screen.getByText(/^Loading/, { selector: ".concept-wiki-title" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Loading article/, { selector: ".concept-wiki-empty" }),
    ).toBeInTheDocument();
  });

  it("loading state shows the Close button", async () => {
    const onClose = vi.fn();
    render(
      <ConceptWikiPane
        {...defaultProps({ loading: true, article: null, onClose })}
      />,
    );
    const closeBtn = screen.getByRole("button", { name: /close pane/i });
    await userEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("ConceptWikiPane — error state", () => {
  it("renders the error message when error is set", () => {
    render(
      <ConceptWikiPane
        {...defaultProps({ error: new Error("boom"), article: null })}
      />,
    );
    expect(screen.getByText("Article not found")).toBeInTheDocument();
    expect(
      screen.getByText(/Could not load this wiki article/),
    ).toBeInTheDocument();
  });

  it("error state shows Regenerate button that fires onRegenerate", async () => {
    const onRegenerate = vi.fn();
    render(
      <ConceptWikiPane
        {...defaultProps({
          error: new Error("404"),
          article: null,
          onRegenerate,
        })}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Regenerate wiki/ }),
    );
    expect(onRegenerate).toHaveBeenCalled();
  });

  it("error state Close button fires onClose", async () => {
    const onClose = vi.fn();
    render(
      <ConceptWikiPane
        {...defaultProps({ error: new Error("x"), article: null, onClose })}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /close pane/i }),
    );
    expect(onClose).toHaveBeenCalled();
  });
});

describe("ConceptWikiPane — empty / null article", () => {
  it("renders nothing when not loading, no error, and no article", () => {
    const { container } = render(
      <ConceptWikiPane {...defaultProps({ article: null })} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("ConceptWikiPane — article render", () => {
  it("renders the article title", () => {
    render(<ConceptWikiPane {...defaultProps()} />);
    expect(
      screen.getByText("Docker Concept", { selector: ".concept-wiki-title" }),
    ).toBeInTheDocument();
  });

  it("renders the markdown body via renderMarkdown (HTML escaped)", () => {
    const { container } = render(<ConceptWikiPane {...defaultProps()} />);
    const body = container.querySelector(".concept-wiki-body");
    expect(body).not.toBeNull();
    // Verify renderMarkdown ran by checking for an emitted <h1>.
    expect(body.innerHTML).toContain("<h1>Docker Concept</h1>");
    // [[Other_Topic]] should be rewritten to a wiki-link anchor
    expect(body.innerHTML).toContain('class="wiki-link"');
    expect(body.innerHTML).toContain('data-wiki-slug="Other_Topic"');
  });

  it("renders the Open in Conversations button + fires callback with article title", async () => {
    const onOpenInConversations = vi.fn();
    render(
      <ConceptWikiPane {...defaultProps({ onOpenInConversations })} />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Open in Conversations/ }),
    );
    expect(onOpenInConversations).toHaveBeenCalledWith("Docker Concept");
  });

  it("renders the Close button + fires onClose", async () => {
    const onClose = vi.fn();
    render(<ConceptWikiPane {...defaultProps({ onClose })} />);
    await userEvent.click(screen.getByRole("button", { name: /close pane/i }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("ConceptWikiPane — breadcrumb", () => {
  it("does not render the breadcrumb nav when breadcrumb is empty", () => {
    const { container } = render(
      <ConceptWikiPane {...defaultProps({ breadcrumb: [] })} />,
    );
    expect(container.querySelector(".wiki-breadcrumb")).toBeNull();
  });

  it("renders one button per breadcrumb entry plus the current title span", () => {
    render(
      <ConceptWikiPane
        {...defaultProps({ breadcrumb: ["Community_1", "K8s"] })}
      />,
    );
    // Slug rendered with underscores replaced by spaces in the button text.
    expect(screen.getByRole("button", { name: "Community 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "K8s" })).toBeInTheDocument();
    // Current article title appears as a span (not a button).
    expect(
      screen.getByText("Docker Concept", {
        selector: ".wiki-breadcrumb-current",
      }),
    ).toBeInTheDocument();
  });

  it("clicking a breadcrumb entry fires onJumpToBreadcrumb with its index", async () => {
    const onJumpToBreadcrumb = vi.fn();
    render(
      <ConceptWikiPane
        {...defaultProps({
          breadcrumb: ["Community_1", "K8s"],
          onJumpToBreadcrumb,
        })}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "K8s" }));
    expect(onJumpToBreadcrumb).toHaveBeenCalledWith(1);
  });
});

describe("ConceptWikiPane — wiki link delegation", () => {
  it("clicking a wiki-link anchor inside the body fires onSlugClick with the slug", async () => {
    const onSlugClick = vi.fn();
    const { container } = render(
      <ConceptWikiPane {...defaultProps({ onSlugClick })} />,
    );
    const wikiLink = container.querySelector(".wiki-link");
    expect(wikiLink).not.toBeNull();
    await userEvent.click(wikiLink);
    expect(onSlugClick).toHaveBeenCalledWith("Other_Topic");
  });

  it("clicking inside the body but outside any wiki-link is a no-op", () => {
    const onSlugClick = vi.fn();
    const { container } = render(
      <ConceptWikiPane {...defaultProps({ onSlugClick })} />,
    );
    const body = container.querySelector(".concept-wiki-body");
    fireEvent.click(body);
    expect(onSlugClick).not.toHaveBeenCalled();
  });

  it("does not fire onSlugClick when the wiki-link has no data-wiki-slug attribute", () => {
    const onSlugClick = vi.fn();
    const articleWithBareLink = {
      slug: "x",
      title: "X",
      markdown: "<a class=\"wiki-link\">no slug</a>", // raw HTML — escaped, never produces a wiki-link
    };
    const { container } = render(
      <ConceptWikiPane
        {...defaultProps({ article: articleWithBareLink, onSlugClick })}
      />,
    );
    const body = container.querySelector(".concept-wiki-body");
    fireEvent.click(body);
    expect(onSlugClick).not.toHaveBeenCalled();
  });
});
