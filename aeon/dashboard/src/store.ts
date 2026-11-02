import { create } from "zustand";
import {
  type Agent, type Approval, type AuditEntry, type InvariantReport, type LedgerEntry,
  type PayoutItem, type PublicConfig, type Role, type StreamEvent, type Trade, type ExecutionEvidence, type Dispute, type HackathonReadiness,
  api, getAuthState, getToken, setAuthState, setToken,
} from "./api";

export type Tab = "ledger" | "trades" | "payouts" | "agents" | "approvals" | "audit";

interface ConsoleState {
  booted: boolean;
  config: PublicConfig | null;
  role: Role | null;
  quotas: { scenarios_left: number } | null;
  agents: Agent[];
  trades: Trade[];
  entries: LedgerEntry[];
  payouts: PayoutItem[];
  batches: any[];
  approvals: Approval[];
  audit: AuditEntry[];
  invariant: InvariantReport | null;
  killSwitch: { active: boolean; reason?: string } ;
  status: any | null;
  workers: any[];
  events: StreamEvent[];
  selectedTradeId: string | null;
  transcript: any[];
  evidence: ExecutionEvidence | null;
  dispute: Dispute | null;
  readiness: HackathonReadiness | null;
  tab: Tab;
  busy: string | null;
  toast: { text: string; kind: "ok" | "error" } | null;
  pendingFunding: { id: string; agentId: string } | null;

  bootstrap: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  judge: () => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  selectTrade: (id: string | null) => Promise<void>;
  openDispute: (reason: string) => Promise<void>;
  resolveDispute: (outcome: "refund" | "release", note: string) => Promise<void>;
  runTrade: (buyerId: string, sellerId: string, job: "image_resize" | "matrix_multiply") => Promise<void>;
  runSettlement: () => Promise<void>;
  runScenario: (name: string) => Promise<void>;
  toggleKillSwitch: () => Promise<void>;
  decide: (id: string, decision: "APPROVED" | "REJECTED") => Promise<void>;
  toggleAgent: (agent: Agent) => Promise<void>;
  fund: (agentId: string, amountMicro: number) => Promise<void>;
  capturePendingFunding: () => Promise<void>;
  showTreasurer: () => Promise<void>;
  resetDemo: () => Promise<void>;
  setTab: (tab: Tab) => void;
  pushEvent: (event: StreamEvent) => void;
  setEvents: (events: StreamEvent[]) => void;
  notify: (text: string, kind?: "ok" | "error") => void;
  clearToast: () => void;
}

const MAX_EVENTS = 300;
let bootstrapStarted = false;

// SSE replay on reconnect can resend events the client already has, so merge by
// id instead of appending blindly.
function mergeEvents(existing: StreamEvent[], incoming: StreamEvent[]): StreamEvent[] {
  const byId = new Map<string, StreamEvent>();
  for (const event of [...existing, ...incoming]) byId.set(event.id, event);
  return [...byId.values()].sort((a, b) => a.seq - b.seq).slice(-MAX_EVENTS);
}

export const useConsole = create<ConsoleState>((set, get) => ({
  booted: false,
  config: null,
  role: null,
  quotas: null,
  agents: [],
  trades: [],
  entries: [],
  payouts: [],
  batches: [],
  approvals: [],
  audit: [],
  invariant: null,
  killSwitch: { active: false },
  status: null,
  workers: [],
  events: [],
  selectedTradeId: null,
  transcript: [],
  evidence: null,
  dispute: null,
  readiness: null,
  tab: "trades",
  busy: null,
  toast: null,
  pendingFunding: null,

  bootstrap: async () => {
    if (bootstrapStarted) return;
    bootstrapStarted = true;
    try {
      const config = await api.config();
      set({ config, booted: true });
      if (getToken()) {
        const auth = getAuthState();
        if (auth) {
          set({ role: auth.role, quotas: auth.quotas });
          await get().refresh();
        } else {
          setToken(null);
        }
      }
      if (getToken()) {
        const recent = await api.recentEvents(0);
        set({ events: recent.events.slice(-MAX_EVENTS) });
      }

      // A funding order awaiting buyer approval survives the PayPal round trip.
      const pending = localStorage.getItem("aeon.pendingFunding");
      if (pending) set({ pendingFunding: { id: pending, agentId: "" } });
      if (pending && new URLSearchParams(window.location.search).get("funding") === "return") {
        await get().capturePendingFunding();
      }
    } catch {
      set({ booted: true });
    }
  },

  login: async (email, password) => {
    const session = await api.login(email, password);
    setToken(session.token);
    setAuthState(session.role, session.quotas);
    set({ role: session.role, quotas: session.quotas });
    void get().refresh();
  },

  signup: async (email, password) => {
    const session = await api.signup(email, password);
    setToken(session.token);
    setAuthState(session.role, session.quotas);
    set({ role: session.role, quotas: session.quotas });
    void get().refresh();
  },

  judge: async () => {
    const session = await api.judge();
    setToken(session.token);
    setAuthState("judge", session.quotas);
    set({ role: "judge", quotas: session.quotas });
    await get().refresh();
  },

  logout: () => {
    setToken(null);
    set({ role: null, quotas: null, agents: [], trades: [], entries: [] });
  },

  refresh: async () => {
    if (!getToken()) return;
    const results = await Promise.allSettled([
      api.agents(), api.trades(), api.entries(), api.payouts(), api.batches(),
      api.approvals(), api.audit(), api.invariant(), api.status(), api.workers(), api.readiness(),
    ]);
    if (!getToken()) {
      set({
        role: null,
        quotas: null,
        agents: [],
        trades: [],
        entries: [],
        payouts: [],
        batches: [],
        approvals: [],
        audit: [],
        invariant: null,
        status: null,
        workers: [],
      });
      return;
    }
    const value = <T,>(index: number): T | null =>
      results[index].status === "fulfilled" ? (results[index] as PromiseFulfilledResult<T>).value : null;
    const agents = value<{ agents: Agent[] }>(0);
    const trades = value<{ trades: Trade[] }>(1);
    const entries = value<{ entries: LedgerEntry[] }>(2);
    const payouts = value<{ payouts: PayoutItem[] }>(3);
    const batches = value<{ settlements: any[] }>(4);
    const approvals = value<{ approvals: Approval[] }>(5);
    const audit = value<{ audit: AuditEntry[] }>(6);
    const invariant = value<InvariantReport>(7);
    const status = value<any>(8);
    const workers = value<{ workers: any[] }>(9);
    const readiness = value<HackathonReadiness>(10);
    set({
      agents: agents?.agents ?? get().agents,
      trades: trades?.trades ?? get().trades,
      entries: entries?.entries ?? get().entries,
      payouts: payouts?.payouts ?? get().payouts,
      batches: batches?.settlements ?? get().batches,
      approvals: approvals?.approvals ?? get().approvals,
      audit: audit?.audit ?? get().audit,
      invariant: invariant ?? get().invariant,
      status: status ?? get().status,
      killSwitch: status?.kill_switch ?? get().killSwitch,
      workers: workers?.workers ?? get().workers,
      readiness: readiness ?? get().readiness,
    });
  },

  selectTrade: async (id) => {
    set({ selectedTradeId: id, transcript: [], evidence: null, dispute: null });
    if (!id) return;
    try {
      const [detail, evidence, dispute] = await Promise.all([
        api.trade(id), api.evidence(id).catch(() => null), api.dispute(id).catch(() => null),
      ]);
      set({ transcript: detail.negotiation_transcript ?? [], evidence: evidence?.evidence ?? null,
        dispute: dispute ?? null });
    } catch {
      set({ transcript: [] });
    }
  },

  openDispute: async (reason) => {
    const id = get().selectedTradeId;
    if (!id) return;
    try {
      const dispute = await api.createDispute(id, reason);
      set({ dispute, toast: { text: "Dispute opened and funds held", kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "could not open dispute", kind: "error" } });
    }
  },

  resolveDispute: async (outcome, note) => {
    const id = get().selectedTradeId;
    if (!id) return;
    try {
      const dispute = await api.resolveDispute(id, outcome, note);
      set({ dispute, toast: { text: `Dispute ${outcome}d`, kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "could not resolve dispute", kind: "error" } });
    }
  },

  runTrade: async (buyerId, sellerId, job) => {
    set({ busy: "Running trade…" });
    try {
      const jobSpec = job === "matrix_multiply"
        ? { type: job, size: 160, params: { n: 160 }, deadline_s: 30 }
        : { type: job, size: 640 * 480, params: { width: 320, height: 240 }, deadline_s: 30 };
      const trade = await api.runTrade(buyerId, jobSpec, sellerId || undefined);
      set({ toast: { text: `Trade ${trade.id.slice(0, 12)} → ${trade.state}`, kind: trade.state === "SETTLED" ? "ok" : "error" } });
      await get().selectTrade(trade.id);
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "trade failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  runSettlement: async () => {
    set({ busy: "Settling…" });
    try {
      const batch = await api.settlement();
      set({ toast: { text: `Settlement ${batch.state ?? "submitted"}`, kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "settlement failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  runScenario: async (name) => {
    set({ busy: `Running ${name}…` });
    try {
      const run = await api.scenario(name);
      set({ toast: { text: `${name}: ${run.state}`, kind: run.state === "COMPLETED" ? "ok" : "error" } });
      const me = await api.me().catch(() => null);
      if (me) set({ quotas: me.quotas });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "scenario failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  toggleKillSwitch: async () => {
    const active = !get().killSwitch.active;
    try {
      await api.killSwitch(active, active ? "Operator pressed the kill switch" : "Operator resumed the system");
      set({ killSwitch: { active }, toast: { text: active ? "Kill switch ACTIVE — writes blocked" : "System resumed", kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "kill switch failed", kind: "error" } });
    }
  },

  decide: async (id, decision) => {
    try {
      await api.decide(id, decision);
      set({ toast: { text: `Approval ${decision.toLowerCase()}`, kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "decision failed", kind: "error" } });
    }
  },

  toggleAgent: async (agent) => {
    try {
      if (agent.status === "ACTIVE") await api.pause(agent.id);
      else await api.resume(agent.id);
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "agent update failed", kind: "error" } });
    }
  },

  fund: async (agentId, amountMicro) => {
    set({ busy: "Creating PayPal order…" });
    try {
      const funding = await api.createFunding(agentId, amountMicro);
      // Mock orders are captured inline. A real sandbox order must be approved
      // by the payer first, so open PayPal and remember it for the return leg.
      if (!funding.mock && funding.approve_url) {
        localStorage.setItem("aeon.pendingFunding", funding.id);
        set({
          pendingFunding: { id: funding.id, agentId },
          toast: { text: "PayPal order created — approve it in the PayPal tab, then click Capture.", kind: "ok" },
        });
        window.open(funding.approve_url, "aeon-paypal", "noopener,noreferrer");
        return;
      }
      await api.captureFunding(funding.id);
      set({ toast: { text: `Funded ${agentId} (${funding.mock ? "simulated PayPal" : "sandbox"})`, kind: "ok" } });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "funding failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  capturePendingFunding: async () => {
    const id = get().pendingFunding?.id || localStorage.getItem("aeon.pendingFunding");
    if (!id) return;
    set({ busy: "Capturing PayPal order…" });
    try {
      const funding = await api.captureFunding(id);
      localStorage.removeItem("aeon.pendingFunding");
      set({
        pendingFunding: null,
        toast: { text: `Captured ${funding.amount_micro} µUSD for ${funding.agent_id}`, kind: "ok" },
      });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "capture failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  showTreasurer: async () => {
    try {
      const plan = await api.treasurerPlan();
      const verdict = plan.treasurer.guardrail?.passed === false
        ? `guardrail: ${plan.treasurer.guardrail.failed.join(", ")}`
        : "guardrail ok";
      set({
        toast: {
          text: `Treasurer (${plan.treasurer.llm.source}): ${plan.treasurer.note} — ${plan.totals.items} item(s), ${plan.totals.amount_micro} µUSD payable, ${verdict}`,
          kind: plan.treasurer.recommend ? "ok" : "error",
        },
      });
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "treasurer unavailable", kind: "error" } });
    }
  },

  resetDemo: async () => {
    set({ busy: "Resetting demo…" });
    try {
      await api.resetDemo();
      set({ toast: { text: "Demo reset: five agents reseeded", kind: "ok" }, selectedTradeId: null, transcript: [] });
      await get().refresh();
    } catch (error) {
      set({ toast: { text: error instanceof Error ? error.message : "reset failed", kind: "error" } });
    } finally {
      set({ busy: null });
    }
  },

  setTab: (tab) => set({ tab }),

  pushEvent: (event) =>
    set((state) => ({ events: mergeEvents(state.events, [event]) })),

  setEvents: (events) => set({ events: mergeEvents([], events) }),

  notify: (text, kind = "ok") => set({ toast: { text, kind } }),

  clearToast: () => set({ toast: null }),
}));
