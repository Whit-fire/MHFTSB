import { useState, useEffect, useRef, useCallback } from 'react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const WS_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws';

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [positions, setPositions] = useState([]);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'log') {
            setLogs(prev => {
              const next = [...prev, msg];
              return next.length > 500 ? next.slice(-500) : next;
            });
          } else if (msg.type === 'metrics_update') {
            setMetrics(msg.data);
            if (msg.positions) setPositions(msg.positions);
          }
        } catch (e) { /* ignore */ }
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      reconnectTimer.current = setTimeout(connect, 3000);
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connect]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { connected, logs, metrics, positions, clearLogs };
}
