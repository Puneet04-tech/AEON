import React from "react";

interface NegotiationRound {
  round: number;
  from: string;
  to: string;
  offer?: string;
  counter?: string;
  reasoning: string;
  status?: "offered" | "countered" | "agreed" | "rejected";
}

const NegotiationTranscript: React.FC = () => {
  const rounds: NegotiationRound[] = [
    {
      round: 1,
      from: "ATLAS",
      to: "BOREALIS",
      reasoning: "Worker load high. S1 profile path.",
    },
    {
      round: 2,
      from: "BOREALIS",
      to: "ATLAS",
      counter: "0.046 uUSD/cpu_sec",
      reasoning: "Energy surges detected via weather data.",
    },
    {
      round: 3,
      from: "ATLAS",
      to: "BOREALIS",
      offer: "0.043 uUSD/cpu_sec",
      status: "agreed",
      reasoning: "Guardrail: PASSED",
    },
  ];

  return (
    <div style={{ 
      flex: 1,
      padding: "8px 12px",
      overflowY: "auto",
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: "11px",
      color: "var(--neutral-text-mid)",
    }}>
      {rounds.map((round, idx) => {
        const isLast = idx === rounds.length - 1;
        const statusStyle = round.status 
          ? `color: ${round.status === "agreed" ? "var(--semantic-in)" : "var(--semantic-risk)"};`
          : "";
        
        const counterStyle = round.counter 
          ? `border-left: 2px solid var(--semantic-out); padding-left: 8px;`
          : "";
        
        return (
          <div
            key={round.round}
            style={{
              padding: "8px 0",
              borderBottom: "1px solid var(--neutral-border)",
              display: "flex",
              alignItems: "flex-start",
            }}
          >
            <span style={{ 
              fontSize: "10px", 
              opacity: 0.5,
              marginRight: "12px",
            }}>
              [Round {round.round}/3]
            </span>
            <span 
              style={{ 
                ...statusStyle,
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
              }}>
              {round.from} -> {round.to}
            </span>
            
            {round.offer && (
              <span 
                style={{ 
                  marginLeft: "auto", 
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "10px",
                  opacity: 0.8,
                }}>
                ├─ Offer: {round.offer}
              </span>
            )}

            {round.counter && (
              <span 
                style={{ 
                  marginLeft: "auto", 
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "10px",
                  opacity: 0.8,
                }}>
                ├─ Counter: {round.counter}
              </span>
            )}

            <span 
              style={{ 
                marginLeft: "auto", 
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "10px",
                opacity: 0.7,
              }}>
              └─ {round.reasoning}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default NegotiationTranscript;