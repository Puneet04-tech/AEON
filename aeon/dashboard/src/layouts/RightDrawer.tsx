import React from "react";
import { useTheme } from "../state/themeState";
import { SSELogStream } from "../components/SSELogStream";
import { NegotiationTranscript } from "../components/NegotiationTranscript";

const RightDrawer: React.FC = () => {
  const { theme } = useTheme();

  return (
    <aside className="right-stream-drawer">
      <div style={{
        background: theme === "dark" ? "#1A1E24" : "#EBF0F5",
        border: "1px solid var(--neutral-border-strong)",
        padding: "12px",
        height: "calc(100% - 40px)",
        overflowY: "auto",
      }}>
        <h3 style={{
          fontSize: "12px",
          fontFamily: "'IBM Plex Sans', sans-serif",
          color: theme === "dark" ? "#94A6BF" : "#4A5564",
          margin: "0 0 12px 0",
          borderBottom: "1px solid var(--neutral-border)",
          paddingBottom: "8px",
        }}>
          LIVE AGENT NEGOTIATION TRANSCRIPT
        </h3>
        <NegotiationTranscript />
        
        <h3 style={{
          fontSize: "12px",
          fontFamily: "'IBM Plex Sans', sans-serif",
          color: theme === "dark" ? "#94A6BF" : "#4A5564",
          margin: "12px 0 0 0",
          borderBottom: "1px solid var(--neutral-border)",
          paddingBottom: "8px",
        }}>
          LIVE SSE LOG
        </h3>
        <SSELogStream />
      </div>
    </aside>
  );
};

export default RightDrawer;