import { useCallback, useEffect, useRef, useState } from "react";

import { applyZoneEvent, validateZoneMap } from "../lib/zoneMap.js";

/** Load local layout and maintain only configured device conditions in memory. */
export function useZoneMap() {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [state, setState] = useState({});
  const configRef = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/zone-map.json", { signal: controller.signal, cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Falha ao carregar cadastro do mapa.");
        return response.json();
      })
      .then(validateZoneMap)
      .then((value) => {
        if (controller.signal.aborted) return;
        configRef.current = value;
        setConfig(value);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      });
    return () => controller.abort();
  }, []);
  const acceptEvent = useCallback((event) => {
    setState((current) => applyZoneEvent(current, event, configRef.current));
  }, []);
  const reset = useCallback(() => setState({}), []);
  return { config, error, state, acceptEvent, reset };
}
