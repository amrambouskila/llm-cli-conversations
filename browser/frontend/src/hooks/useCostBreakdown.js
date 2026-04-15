import { useEffect, useState } from "react";
import { fetchSessionCostBreakdown } from "../api";

export function useCostBreakdown(sessionId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!sessionId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetchSessionCostBreakdown(sessionId, { signal: controller.signal })
      .then((breakdown) => {
        if (cancelled) return;
        setData(breakdown);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled || err.name === "AbortError") return;
        setError(err);
        setLoading(false);
        setData(null);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [sessionId]);

  return { data, loading, error };
}
