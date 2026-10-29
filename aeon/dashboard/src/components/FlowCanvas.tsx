import React from "react";
import { ReactFlow, addEdge, Edge, addEdgeChange, OnConnect, OnDisconnect, OnNodesDelete, Node, Connection } from "reactflow";
import "reactflow/dist/style.css";

// Node component for AEON agent topology
const AEONNode: React.FC<{ node: Node }> = ({ node }) => {
  const { id, type, position, data } = node;
  
  return (
    <div className="aeon-node-pane" style={{
      left: position.x,
      top: position.y,
      width: 200,
      height: 100,
    }}>
      <div style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        padding: "8px",
        background: "rgba(255,255,255,0.3)",
        backdropFilter: "blur(12px) saturate(110%)",
        borderRadius: "4px 4px 0 0",
      }}>
        <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "11px", color: "#4A5564" }}>
          {data?.label || id}
        </span>
      </div>
      <span style={{
        position: "absolute",
        top: 4,
        left: 4,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: "10px",
        color: "#7E8B9B",
      }}>
        {data?.balance || "0"}
      </span>
    </div>
  );
};

// Edge component for AEON money flows
const AEONEdge: React.FC<{ edge: Connection }> = ({ edge }) => {
  const { id, source, target, type, style, data } = edge;
  
  const color = data?.type === "in" ? "--semantic-in" : 
                data?.type === "out" ? "--semantic-out" : 
                "--accent-solid";
  
  return (
    <Edge
      id={id}
      source={source}
      target={target}
      type={type}
      stroke={color}
      style={{ strokeDasharray: data?.animating ? "4 2" : "6 2" }}
      data={data}
    />
  );
};

const FlowCanvas: React.FC = () => {
  const nodes = [
    { id: "consumer", type: "input", data: { label: "Consumer", balance: "1,245 uUSD", type: "in" } },
    { id: "provider", type: "output", data: { label: "Provider", balance: "892 uUSD", type: "out" } },
    { id: "treasurer", type: "controller", data: { label: "Treasurer", balance: "5,000,000 uUSD", type: "pending" } },
    { id: "lender", type: "controller", data: { label: "Lender", balance: "2,500,000 uUSD", type: "pending" } },
  ];

  const edges = [
    { id: "e1", source: "consumer", target: "provider", data: { type: "in", animating: true } },
    { id: "e2", source: "provider", target: "treasurer", data: { type: "out", animating: true } },
    { id: "e3", source: "lender", target: "treasurer", data: { type: "pending", animating: true } },
  ];

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      style={{ height: "100%", width: "100%" }}
      onConnect={OnConnect}
      onDisconnect={OnDisconnect}
      onNodesDelete={OnNodesDelete}
    >
      {nodes.map((node) => (
        <AEONNode key={node.id} node={node} />
      ))}
      {edges.map((edge) => (
        <AEONEdge key={edge.id} edge={edge} />
      ))}
    </ReactFlow>
  );
};

export default FlowCanvas;