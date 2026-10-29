import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { useConsole, type Tab } from "../store";
import { formatMoney, formatTime } from "../api";

const TABS: { id: Tab; label: string }[] = [
  { id: "trades", label: "Trades" },
  { id: "ledger", label: "Ledger" },
  { id: "payouts", label: "Payouts" },
  { id: "agents", label: "Agents" },
  { id: "approvals", label: "Approvals" },
  { id: "audit", label: "Audit" },
];

const moneyCol = (headerName: string, width: number, valueGetter: (p: any) => number): ColDef => ({
  headerName,
  width,
  valueGetter,
  valueFormatter: (params) => formatMoney(Number(params.value) || 0, false),
  cellStyle: { textAlign: "right" },
});

export default function DataConsole() {
  const state = useConsole();
  const { tab, setTab, selectTrade, decide, toggleAgent, trades, entries, payouts, agents, approvals, audit } = state;

  const columnDefs = useMemo<Record<Tab, ColDef[]>>(() => ({
    trades: [
      { field: "id", headerName: "Trade", width: 190 },
      { field: "state", headerName: "State", width: 150 },
      { field: "buyer_id", headerName: "Buyer", width: 110 },
      { field: "seller_id", headerName: "Seller", width: 110 },
      moneyCol("Price (µUSD)", 130, (p) => p.data?.agreed?.price_micro ?? 0),
      { headerName: "CPU s", width: 80, valueGetter: (p) => p.data?.metering?.cpu_s ?? 0 },
      { headerName: "Rounds", width: 80, valueGetter: (p) => p.data?.attempt ?? 1 },
      moneyCol("Penalty (µUSD)", 130, (p) => p.data?.settlement?.penalty_micro ?? 0),
      { field: "created_at", headerName: "Created", width: 110, valueFormatter: (p) => formatTime(p.value) },
    ],
    ledger: [
      { field: "txn_id", headerName: "Txn", width: 170 },
      { field: "account", headerName: "Account", width: 150 },
      { field: "agent_id", headerName: "Agent", width: 110 },
      moneyCol("Amount (µUSD)", 150, (p) => p.data?.amount_micro ?? 0),
      { field: "memo", headerName: "Memo", flex: 1, minWidth: 180 },
      { headerName: "Posted", width: 100, valueGetter: (p) => formatTime(p.data?.posted_at) },
    ],
    payouts: [
      { field: "settlement_id", headerName: "Batch", width: 180 },
      { field: "agent_id", headerName: "Agent", width: 110 },
      { field: "receiver", headerName: "Receiver", width: 210 },
      moneyCol("Amount (µUSD)", 140, (p) => p.data?.amount_micro ?? 0),
      { field: "state", headerName: "State", width: 110 },
      { field: "paypal_item_id", headerName: "PayPal item", flex: 1, minWidth: 170 },
    ],
    agents: [
      { field: "name", headerName: "Agent", width: 130 },
      { field: "role", headerName: "Role", width: 100 },
      { field: "status", headerName: "Status", width: 100 },
      moneyCol("Available", 140, (p) => p.data?.balances?.available_micro ?? 0),
      moneyCol("Escrow", 110, (p) => p.data?.balances?.escrow_micro ?? 0),
      moneyCol("Bond", 110, (p) => p.data?.balances?.bond_micro ?? 0),
      { headerName: "Uptime", width: 90, valueGetter: (p) => p.data?.risk?.uptime_30d ?? 0 },
      { headerName: "Late", width: 70, valueGetter: (p) => p.data?.risk?.late_count ?? 0 },
      { headerName: "Action", width: 90, colId: "toggle_agent", valueGetter: () => "" },
    ],
    approvals: [
      { field: "kind", headerName: "Kind", width: 120 },
      { headerName: "Subject", width: 200, valueGetter: (p) => p.data?.subject?.id ?? "" },
      moneyCol("Amount (µUSD)", 150, (p) => p.data?.amount_micro ?? 0),
      { field: "state", headerName: "State", width: 120 },
      { headerName: "Expires", width: 100, valueGetter: (p) => formatTime(p.data?.expires_at) },
      { headerName: "Decision", width: 150, colId: "decide", valueGetter: () => "" },
    ],
    audit: [
      { headerName: "At", width: 100, valueGetter: (p) => formatTime(p.data?.at) },
      { field: "action", headerName: "Action", width: 210 },
      { headerName: "Actor", width: 150, valueGetter: (p) => `${p.data?.actor?.type}:${p.data?.actor?.id}` },
      { headerName: "Subject", width: 210, valueGetter: (p) => `${p.data?.subject?.type}:${p.data?.subject?.id}` },
      { field: "severity", headerName: "Severity", width: 100 },
    ],
  }), []);

  const rowData = useMemo(() => {
    switch (tab) {
      case "trades": return trades;
      case "ledger": return entries;
      case "payouts": return payouts;
      case "agents": return agents;
      case "approvals": return approvals;
      case "audit": return audit;
      default: return [];
    }
  }, [tab, trades, entries, payouts, agents, approvals, audit]);

  return (
    <section className="console-panel">
      <nav className="tabs">
        {TABS.map((item) => (
          <button key={item.id} className={`tab ${tab === item.id ? "active" : ""}`}
                  onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="grid-wrap ag-theme-quartz">
        {rowData.length === 0 ? (
          <div className="empty">
            {tab === "trades" ? "No trades yet — press Run trade to start one." : `No ${tab} rows yet.`}
          </div>
        ) : (
          <AgGridReact
            rowData={rowData as any[]}
            columnDefs={columnDefs[tab]}
            defaultColDef={{ sortable: true, resizable: true, suppressHeaderMenuButton: true }}
            getRowId={(params) => params.data.id ?? params.data.txn_id ?? params.data.event_id ?? Math.random().toString(36)}
            rowSelection="single"
            suppressCellFocus
            onRowClicked={(event) => {
              if (tab === "trades") selectTrade(event.data.id);
            }}
            onCellClicked={(event) => {
              if (tab === "agents" && event.colDef.colId === "toggle_agent") {
                toggleAgent(event.data);
              }
              if (tab === "approvals" && event.colDef.colId === "decide" && event.data.state === "PENDING") {
                decide(event.data.id, "APPROVED");
              }
            }}
            onCellDoubleClicked={(event) => {
              if (tab === "approvals" && event.data.state === "PENDING") {
                decide(event.data.id, "REJECTED");
              }
            }}
          />
        )}
      </div>
    </section>
  );
}
