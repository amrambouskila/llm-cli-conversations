import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../api", () => ({
  deleteSummary: vi.fn(() => Promise.resolve({ ok: true })),
}));

import SummaryPanel from "../components/SummaryPanel";
import { deleteSummary } from "../api";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SummaryPanel — empty state", () => {
  it("renders 'Select a request' when summaryKey is null", () => {
    render(
      <SummaryPanel
        summaryKey={null}
        onRequest={() => Promise.resolve({})}
        onPoll={() => Promise.resolve({})}
      />
    );
    expect(
      screen.getByText("Select a request to see its summary")
    ).toBeInTheDocument();
  });

});

describe("SummaryPanel — immediate-ready path", () => {
  it("sets status=ready and renders summary when onRequest resolves immediately", async () => {
    const onRequest = vi.fn(() =>
      Promise.resolve({ status: "ready", summary: "Hello summary" })
    );
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText("Hello summary")).toBeInTheDocument()
    );
  });

  it("calls onTitleReady when onRequest returns a title", async () => {
    const onTitleReady = vi.fn();
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({
            status: "ready",
            summary: "x",
            title: "Hello Title",
          })
        }
        onPoll={() => Promise.resolve({})}
        onTitleReady={onTitleReady}
      />
    );
    await waitFor(() =>
      expect(onTitleReady).toHaveBeenCalledWith("s1", "Hello Title")
    );
  });

  it("does NOT call onTitleReady when title is absent", async () => {
    const onTitleReady = vi.fn();
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({ status: "ready", summary: "x" })
        }
        onPoll={() => Promise.resolve({})}
        onTitleReady={onTitleReady}
      />
    );
    await waitFor(() =>
      expect(screen.queryByText(/Generating summary/)).not.toBeInTheDocument()
    );
    expect(onTitleReady).not.toHaveBeenCalled();
  });

  it("renders Regenerate button when status is ready", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "ready", summary: "x" })}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Regenerate" })
      ).toBeInTheDocument()
    );
  });

  it("renders summary as rendered markdown (converts headers/bold)", async () => {
    const { container } = render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({ status: "ready", summary: "# Title\n\n**bold**" })
        }
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => {
      expect(container.querySelector("h1")).not.toBeNull();
    });
    expect(container.querySelector("strong")).not.toBeNull();
  });
});

describe("SummaryPanel — pending state", () => {
  it("shows loading text 'Starting summary...' immediately after mount", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => new Promise(() => {})}
        onPoll={() => Promise.resolve({})}
      />
    );
    expect(screen.getByText(/Starting summary/)).toBeInTheDocument();
  });

  it("does NOT show Regenerate button in pending state", () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => new Promise(() => {})}
        onPoll={() => Promise.resolve({})}
      />
    );
    expect(
      screen.queryByRole("button", { name: "Regenerate" })
    ).not.toBeInTheDocument();
  });
});

describe("SummaryPanel — progress formatting fallback cases", () => {
  it("formatProgress returns 'Summarizing requests...' when p.total=0 (line 24 false branch)", async () => {
    const onRequest = vi.fn().mockResolvedValue({
      status: "pending",
      progress: { phase: "segments", done: 0, total: 0, level: 0 },
    });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Summarizing requests\.\.\./)).toBeInTheDocument()
    );
  });

  it("formatProgress returns 'Combining summaries...' when rollup p.total=0", async () => {
    const onRequest = vi.fn().mockResolvedValue({
      status: "pending",
      progress: { phase: "rollup", done: 0, total: 0, level: 0 },
    });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Combining summaries\.\.\./)).toBeInTheDocument()
    );
  });
});

describe("SummaryPanel — progress formatting", () => {
  it("shows 'Summarizing requests (N/M)' when phase=segments with total", async () => {
    const onRequest = vi.fn(() =>
      Promise.resolve({
        status: "pending",
        progress: { phase: "segments", done: 3, total: 10 },
      })
    );
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => new Promise(() => {})}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Summarizing requests \(3\/10\)/)
      ).toBeInTheDocument()
    );
  });

  it("shows 'Summarizing requests...' when phase=segments with no total", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({
            status: "pending",
            progress: { phase: "segments", done: 0, total: 0 },
          })
        }
        onPoll={() => new Promise(() => {})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Summarizing requests\.\.\./)).toBeInTheDocument()
    );
  });

  it("shows 'Combining summaries (level N, done/total)' when phase=rollup with total", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({
            status: "pending",
            progress: { phase: "rollup", level: 1, done: 2, total: 5 },
          })
        }
        onPoll={() => new Promise(() => {})}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Combining summaries \(level 2, 2\/5\)/)
      ).toBeInTheDocument()
    );
  });

  it("shows 'Combining summaries...' when phase=rollup with no total", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({
            status: "pending",
            progress: { phase: "rollup", level: 0, done: 0, total: 0 },
          })
        }
        onPoll={() => new Promise(() => {})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Combining summaries\.\.\./)).toBeInTheDocument()
    );
  });

  it("shows 'Generating summary...' for unknown phase", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() =>
          Promise.resolve({
            status: "pending",
            progress: { phase: "mystery" },
          })
        }
        onPoll={() => new Promise(() => {})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Generating summary\.\.\./)).toBeInTheDocument()
    );
  });
});

describe("SummaryPanel — polling to ready", () => {
  it("poll loop transitions to ready and renders summary", async () => {
    vi.useFakeTimers();
    const onRequest = vi.fn(() => Promise.resolve({ status: "pending" }));
    const onPoll = vi
      .fn()
      .mockResolvedValueOnce({ status: "pending" })
      .mockResolvedValueOnce({ status: "ready", summary: "Poll done" });

    render(
      <SummaryPanel summaryKey="s1" onRequest={onRequest} onPoll={onPoll} />
    );

    // Let the initial promise resolve so polling is set up
    await act(async () => {
      await Promise.resolve();
    });
    // Advance 2s twice to trigger two polls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(screen.getByText("Poll done")).toBeInTheDocument();
  });

  it("updates progress and resets idle timer on progress advance", async () => {
    vi.useFakeTimers();
    const onPoll = vi
      .fn()
      .mockResolvedValueOnce({
        status: "pending",
        progress: { phase: "segments", done: 1, total: 5 },
      })
      .mockResolvedValueOnce({
        status: "pending",
        progress: { phase: "segments", done: 3, total: 5 },
      })
      .mockResolvedValue({ status: "pending" });

    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={onPoll}
      />
    );

    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText(/Summarizing requests \(1\/5\)/)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText(/Summarizing requests \(3\/5\)/)).toBeInTheDocument();
  });

  it("calls onTitleReady when poll returns a title", async () => {
    vi.useFakeTimers();
    const onTitleReady = vi.fn();
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={() =>
          Promise.resolve({ status: "ready", summary: "x", title: "T" })
        }
        onTitleReady={onTitleReady}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(onTitleReady).toHaveBeenCalledWith("s1", "T");
  });

  it("keeps polling through poll errors (does not stop on thrown onPoll)", async () => {
    vi.useFakeTimers();
    const onPoll = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce({ status: "ready", summary: "recovered" });

    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={onPoll}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});

describe("SummaryPanel — idle timeout", () => {
  it("switches to no-watcher state after 5 minutes with no progress advance", async () => {
    vi.useFakeTimers();
    const onPoll = vi.fn().mockResolvedValue({ status: "pending" });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={onPoll}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000 + 100);
    });
    expect(
      screen.getByText(/AI CLI Not Detected/)
    ).toBeInTheDocument();
  });

  it("shows install instructions in no-watcher state", async () => {
    vi.useFakeTimers();
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={() => Promise.resolve({ status: "pending" })}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000 + 100);
    });
    expect(screen.getByText(/Install AI CLI/)).toBeInTheDocument();
    expect(screen.getByText(/Authenticate:/)).toBeInTheDocument();
    expect(screen.getByText(/Restart the service:/)).toBeInTheDocument();
  });

  it("shows Regenerate button in no-watcher state", async () => {
    vi.useFakeTimers();
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.resolve({ status: "pending" })}
        onPoll={() => Promise.resolve({ status: "pending" })}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000 + 100);
    });
    expect(
      screen.getByRole("button", { name: "Regenerate" })
    ).toBeInTheDocument();
  });
});

describe("SummaryPanel — error state", () => {
  it("sets status=error when onRequest throws", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.reject(new Error("bad request"))}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText(/Summary Unavailable/)).toBeInTheDocument()
    );
    expect(screen.getByText("bad request")).toBeInTheDocument();
  });

  it("shows Regenerate button in error state", async () => {
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={() => Promise.reject(new Error("boom"))}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Regenerate" })
      ).toBeInTheDocument()
    );
  });
});

describe("SummaryPanel — regenerate button", () => {
  it("regenerate calls deleteSummary and re-requests", async () => {
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first" })
      .mockResolvedValueOnce({ status: "ready", summary: "regenerated" });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(screen.getByText("regenerated")).toBeInTheDocument()
    );
    expect(deleteSummary).toHaveBeenCalledWith("s1");
  });

  it("regenerate handles onRequest throwing", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first" })
      .mockRejectedValueOnce(new Error("regen failed"));
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(screen.getByText(/Summary Unavailable/)).toBeInTheDocument()
    );
    expect(screen.getByText("regen failed")).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it("regenerate transitions to pending while second onRequest is in-flight", async () => {
    let resolveSecond;
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first" })
      .mockReturnValueOnce(
        new Promise((res) => {
          resolveSecond = res;
        })
      );
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(screen.getByText(/Starting summary/)).toBeInTheDocument()
    );
    resolveSecond({ status: "ready", summary: "second" });
    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());
  });

  it("regenerate ready with title and onTitleReady fires both (line 157)", async () => {
    const onTitleReady = vi.fn();
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first", title: "First" })
      .mockResolvedValueOnce({ status: "ready", summary: "regen", title: "Regen" });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
        onTitleReady={onTitleReady}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    await waitFor(() =>
      expect(onTitleReady).toHaveBeenCalledWith("s1", "Regen")
    );
  });

  it("regenerate when onRequest returns non-ready status triggers startPolling (lines 159-160)", async () => {
    // First onRequest call: immediate ready so we can render + click Regenerate.
    // Second onRequest call (via Regenerate): returns pending with progress.
    // This fires the `else { startPolling(...) }` branch in handleRegenerate.
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first" })
      .mockResolvedValueOnce({
        status: "pending",
        progress: { phase: "segments", done: 0, total: 3, level: 0 },
      });
    // onPoll must keep returning pending so the component stays in the polling state
    // long enough for us to observe the progress message.
    const onPoll = vi.fn().mockResolvedValue({
      status: "pending",
      progress: { phase: "segments", done: 1, total: 3, level: 0 },
    });
    render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={onPoll}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    // startPolling called → progress from the regen response shown
    await waitFor(() =>
      expect(screen.getByText(/Summarizing requests/)).toBeInTheDocument()
    );
  });
});

describe("SummaryPanel — summaryKey changes", () => {
  it("re-requests when summaryKey changes", async () => {
    const onRequest = vi
      .fn()
      .mockResolvedValueOnce({ status: "ready", summary: "first" })
      .mockResolvedValueOnce({ status: "ready", summary: "second" });
    const { rerender } = render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    rerender(
      <SummaryPanel
        summaryKey="s2"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() =>
      expect(screen.getByText("second")).toBeInTheDocument()
    );
    expect(onRequest).toHaveBeenCalledTimes(2);
  });

  it("goes to empty state when summaryKey becomes null after being set", async () => {
    const onRequest = vi.fn(() =>
      Promise.resolve({ status: "ready", summary: "x" })
    );
    const { rerender } = render(
      <SummaryPanel
        summaryKey="s1"
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    await waitFor(() => expect(screen.getByText("x")).toBeInTheDocument());
    rerender(
      <SummaryPanel
        summaryKey={null}
        onRequest={onRequest}
        onPoll={() => Promise.resolve({})}
      />
    );
    expect(
      screen.getByText("Select a request to see its summary")
    ).toBeInTheDocument();
  });
});
