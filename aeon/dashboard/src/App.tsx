import { useEffect, useRef } from "react";
import { streamUrl, type StreamEvent } from "./api";
import { useConsole } from "./store";
import TopBar from "./components/TopBar";
import LeftRailNavigation from "./components/LeftRailNavigation";
import AgentGraph from "./components/AgentGraph";
import DataConsole from "./components/DataConsole";
import EventDrawer from "./components/EventDrawer";
import LoginScreen from "./components/LoginScreen";

export default function App() {
  const { role, booted, bootstrap, config, refresh, pushEvent, toast, clearToast, busy } = useConsole();
  const source = useRef<EventSource | null>(null);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // Poll as a safety net; the SSE stream is the primary live channel.
  useEffect(() => {
    if (!role) return;
    const timer = setInterval(() => refresh(), 8000);
    refresh();
    return () => clearInterval(timer);
  }, [role, refresh]);

  useEffect(() => {
    if (!role) {
      source.current?.close();
      return;
    }
    const eventSource = new EventSource(streamUrl());
    source.current = eventSource;
    const handle = (message: MessageEvent) => {
      try {
        pushEvent(JSON.parse(message.data) as StreamEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    const types = [
      "trade.created", "trade.agreed", "trade.escrowed", "trade.dispatched", "trade.delivered",
      "trade.verified", "trade.settled", "trade.failed", "trade.finished",
      "funding.created", "funding.captured", "settlement.proposed", "settlement.submitted",
      "settlement.succeeded", "settlement.failed", "approval.requested", "approval.decided",
      "loan.decision", "loan.disbursed", "loan.repaid", "worker.chaos", "control.kill_switch",
      "scenario.step", "scenario.finished", "webhook.processed", "agent.paused", "agent.resumed",
    ];
    types.forEach((type) => eventSource.addEventListener(type, handle as EventListener));
    eventSource.onmessage = handle;
    eventSource.onerror = () => {
      // Browsers reconnect automatically; nothing to do here.
    };
    return () => eventSource.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(clearToast, 6000);
    return () => clearTimeout(timer);
  }, [toast, clearToast]);

  if (!booted) return <div className="login-wrap"><div className="empty">Connecting…</div></div>;
  if (!role) return <LoginScreen />;

  return (
    <div className="aeon-workspace-grid">
      <TopBar />
      <LeftRailNavigation />
      <main className="main-operation-theater">
        <AgentGraph />
        <DataConsole />
      </main>
      <EventDrawer />

      {busy && <div className="busy">{busy}</div>}
      {toast && (
        <div className={`toast ${toast.kind}`} onClick={clearToast}>{toast.text}</div>
      )}
    </div>
  );
}
