import { useState, useEffect } from "react";
import { fetchReady } from "../api";

export function useBackendReady() {
  const [backendReady, setBackendReady] = useState(false);

  useEffect(() => {
    let timer = null;
    let cancelled = false;
    const check = () => {
      fetchReady()
        .then((r) => {
          if (cancelled) return;
          if (r.ready) setBackendReady(true);
          else timer = setTimeout(check, 1000);
        })
        .catch(() => {
          if (cancelled) return;
          timer = setTimeout(check, 1000);
        });
    };
    check();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return backendReady;
}
