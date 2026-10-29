import React, { useEffect, useState } from "react";

const SSELogStream: React.FC = () => {
  const [logs, setLogs] = useState<Array<{
    id: number;
    timestamp: number;
    type: "info" | "success" | "warning" | "error";
    message: string;
    agent?: string;
  }>>>([]);

  // Simulate SSE connection - in production would connect to real SSE endpoint
  useEffect(() => {
    // Initial sample logs per DESIGN.md Component 5 spec
    const initialLogs = [
      {
        id: 1,
        timestamp: Date.now(),
        type: "info",
        message: "System initialized. Agent topology ready.",
      },
      {
        id: 2,
        timestamp: Date.now() - 1000,
        type: "info",
        message: "Consumer -> Provider: Offer 0.040 uUSD/cpu_sec",
        agent: "ATLAS",
      },
      {
        id: 3,
        timestamp: Date.now() - 2000,
        type: "success",
        message: "Trade agreed: 0.043 uUSD/cpu_sec",
        agent: "ATLAS",
      },
    ];

    setLogs(initialLogs);

    // Start SSE simulation - poll for new events
    const eventSource = new EventSource("/api/v1/events/stream");

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLogs((prev) => {
        const newLog = {
          id: prev.length + 1,
          timestamp: Date.now(),
          ...data,
        };
        // Keep only last 50 logs
        const updated = [newLog, ...prev].slice(0, 50);
        return updated;
      });
    };

    eventSource.onerror = () => {
      eventSource.close();
      // Fallback: poll every 3 seconds
      const poll = setInterval(() => {
        fetch("/api/v1/events/stream")
          .then((res) => res.json())
          .then((data) => {
            setLogs((prev) => {
              const newLog = {
                id: prev.length + 1,
                timestamp: Date.now(),
                ...data,
              };
              return [newLog, ...prev].slice(0, 50);
            });
          });
      }, 3000);
      return () => clearInterval(poll);
    };

    return () => {
      eventSource.close();
    };
  }, []);

  // Guardrail violation styling per DESIGN.md
  const getLogClass = (type: string) => {
    switch (type) {
      case "success": return "sse-log-entry";
      case "warning": return "sse-log-entry sse-log-guardrail-violation";
      case "error": return "sse-log-entry sse-log-guardrail-violation";
      default: return "sse-log-entry";
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "success": return "var(--semantic-in)";
      case "warning": return "var(--semantic-pending)";
      case "error": return "var(--semantic-risk)";
      default: return "var(--neutral-text-mid)";
    }
  };

  return (
    <div style={{ 
      flex: 1,
      padding: "8px 12px",
      overflowY: "auto",
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: "11px",
      color: "var(--neutral-text-mid)",
      background: "rgba(255,255,255,0.3)",
      backdropFilter: "blur(12px) saturate(110%)",
    }}>
      {logs.map((log) => (
        <div
          key={log.id}
          className={getLogClass(log.type)}
          style={{
            padding: "4px 8px",
            margin: "2px 0",
            borderRadius: "2px",
            color: getTypeColor(log.type),
            borderLeft: "3px solid currentColor",
          }}
        >
          <span style={{ opacity: 0.7, marginRight: "8px" }}>
            {new Date(log.timestamp).toLocaleTimeString()}
          </span>
          <span>
            {log.message}
          </span>
          {log.agent && <span style={{ marginLeft: "16px", opacity: 0.6 }}>({log.agent})</span>}
        </div>
      ))}
      
      {logs.length === 0 && (
        <div style={{ 
          padding: "8px", 
          color: "var(--neutral-text-min)",
          fontStyle: "italic",
        }}>
          No events yet.
        </div>
      )}
    </div>
  );
};

export default SSELogStream;