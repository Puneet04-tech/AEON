import { useEffect, useMemo, useRef } from "react";
import ReactFlow, {
  Background, Controls, MarkerType, type Edge, type Node, useEdgesState, useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { useConsole } from "../store";
import { compactMoney } from "../api";

const ROLE_ORDER: Record<string, number> = { consumer: 0, provider: 1, lender: 2, treasurer: 3 };
const COLUMN_X: Record<string, number> = { consumer: 40, provider: 320, lender: 600, treasurer: 820 };

export default function AgentGraph() {
  const { agents, events, selectedTradeId, selectTrade } = useConsole();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const seen = useRef<Set<string>>(new Set());

  const layout = useMemo(() => {
    const counts: Record<string, number> = {};
    return agents.map((agent) => {
      const role = agent.role;
      counts[role] = (counts[role] ?? 0) + 1;
      return {
        id: agent.id,
        position: { x: COLUMN_X[role] ?? 40, y: 30 + (counts[role] - 1) * 96 },
        data: { agent },
        type: "default",
        style: {
          background: "transparent",
          border: "none",
          padding: 0,
          width: 156,
        },
      } as Node;
    });
  }, [agents]);

  useEffect(() => {
    setNodes(
      layout.map((node) => ({
        ...node,
        data: {
          label: <AgentLabel agent={node.data.agent} />,
        },
      })),
    );
  }, [layout, setNodes]);

  // Animated money edges, driven by live trade events.
  useEffect(() => {
    const created = events.filter((event) =>
      ["trade.created", "trade.escrowed", "trade.delivered", "trade.settled"].includes(event.type),
    );
    const newEdges: Edge[] = [];
    for (const event of created.slice(-12)) {
      const tradeId = String(event.payload.trade_id ?? event.trade_id ?? "");
      const buyer = String(event.payload.buyer_id ?? "");
      const seller = String(event.payload.seller_id ?? "");
      const key = `${tradeId}:${event.type}`;
      if (!buyer || !seller || seen.current.has(key)) continue;
      seen.current.add(key);
      newEdges.push({
        id: key,
        source: buyer,
        target: seller,
        animated: event.type !== "trade.settled",
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        style: {
          stroke: event.type === "trade.settled" ? "var(--semantic-in)" : "var(--accent-solid)",
          strokeWidth: event.type === "trade.settled" ? 1.2 : 1.8,
          opacity: 0.85,
        },
        label: event.type.replace("trade.", ""),
        labelStyle: { fontSize: 9, fill: "var(--neutral-text-min)" },
        labelBgStyle: { fill: "var(--neutral-bg)" },
      });
    }
    if (newEdges.length) {
      setEdges((current) => [...current, ...newEdges].slice(-24));
    }
  }, [events, setEdges]);

  useEffect(() => setEdges([]), [agents.length, setEdges]);

  return (
    <section className="graph-panel">
      <span className="panel-label">Agent topology · live money flow</span>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => selectTrade(selectedTradeId)}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.5}
        maxZoom={1.4}
      >
        <Background gap={22} size={1} color="var(--neutral-border)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </section>
  );
}

function AgentLabel({ agent }: { agent: any }) {
  const available = agent.balances?.available_micro ?? 0;
  const escrow = agent.balances?.escrow_micro ?? 0;
  return (
    <div className={`agent-node ${agent.status !== "ACTIVE" ? "paused" : ""}`}>
      <div className="name">{agent.name}</div>
      <div className="role">{agent.role} · {agent.status}</div>
      <div className="amount">{compactMoney(available)} µUSD avail</div>
      {escrow > 0 && (
        <div style={{ color: "var(--semantic-pending)", fontSize: 10 }}>{compactMoney(escrow)} in escrow</div>
      )}
    </div>
  );
}
