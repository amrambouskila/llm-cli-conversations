import { useState, useEffect } from "react";
import { fetchProviders } from "../api";

export function useProviders() {
  const [providers, setProviders] = useState([]);

  useEffect(() => {
    fetchProviders().then(setProviders).catch(console.error);
  }, []);

  return providers;
}
