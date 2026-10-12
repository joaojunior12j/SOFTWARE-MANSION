import { useCallback, useEffect, useRef, useState } from "react";

import { websocketUrl } from "../lib/alarm.js";

export function useAlarmFeed() {
  const [alarms, setAlarms] = useState([]);
  const [mqttOnline, setMqttOnline] = useState(false);
  const [streamOnline, setStreamOnline] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState("");
  const reconnectAttempt = useRef(0);

  const refreshAlarms = useCallback(async () => {
    const response = await fetch("/api/alarmes/ativos");
    if (!response.ok) throw new Error("Falha ao carregar alarmes ativos");
    setAlarms(await response.json());
    setLastUpdate(new Date());
  }, []);

  const refreshStatus = useCallback(async () => {
    const response = await fetch("/api/status");
    if (!response.ok) throw new Error("Falha ao consultar o barramento");
    const status = await response.json();
    setMqttOnline(status.mqtt_online);
  }, []);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let refreshTimer;
    let stopped = false;

    const reportError = (reason) => {
      if (stopped) return;
      setError(reason instanceof Error ? reason.message : String(reason));
    };

    const loadInitialState = async () => {
      try {
        await Promise.all([refreshAlarms(), refreshStatus()]);
        if (stopped) return;
        setError("");
      } catch (reason) {
        reportError(reason);
      }
    };

    const connect = () => {
      socket = new WebSocket(websocketUrl());
      socket.onopen = () => {
        if (stopped) return;
        reconnectAttempt.current = 0;
        setStreamOnline(true);
        setError("");
        refreshStatus().catch(reportError);
      };
      socket.onmessage = () => {
        if (stopped) return;
        setLastUpdate(new Date());
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => {
          refreshAlarms().catch(reportError);
          refreshStatus().catch(reportError);
        }, 350);
      };
      socket.onerror = () => {
        if (!stopped) setError("Fluxo de eventos indisponível");
      };
      socket.onclose = () => {
        if (stopped) return;
        setStreamOnline(false);
        setMqttOnline(false);
        reconnectAttempt.current += 1;
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 10000);
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    loadInitialState();
    connect();
    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      clearTimeout(refreshTimer);
      socket?.close();
    };
  }, [refreshAlarms, refreshStatus]);

  return {
    alarms,
    error,
    lastUpdate,
    mqttOnline,
    refreshAlarms,
    streamOnline,
  };
}
