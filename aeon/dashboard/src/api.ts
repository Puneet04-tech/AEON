/** Typed API client for the AEON console. */

export type Role = "operator" | "judge";

export interface PublicConfig {
  environment: string;
  paypal_mode: "sandbox" | "unconfigured" | "mock";
  paypal_env: string;
  llm_mode: string;
  judge_session_minutes: number;
  judge_scenario_quota: number;
  operator_login: boolean;
  currency: string;
  money_unit: string;
  disclosures: string[];
}

export interface Balances {
  available_micro: number;
  escrow_micro: number;
  bond_micro: number;
  total_micro: number;
}

export interface Agent {
  id: string;
  name: string;
  role: "consumer" | "provider" | "treasurer" | "lender";
  status: "ACTIVE" | "PAUSED" | "SUSPENDED";
  region_label: string;
  paypal_email: string;
  profile: { capacity_cpu_s_per_min: number; base_cost_micro: number; worker_url: string };
  policy: {
    per_trade_cap_micro: number;
    daily_cap_micro: number;
    price_band_bps: number;
    allowlist: string[];
    approval_threshold_micro: number;
    velocity_per_min: number;
    cash_out?: boolean;
  };
  risk: { uptime_30d: number; late_count: number };
  balances?: Balances;
}

export interface Trade {
  id: string;
  job_id: string;
  buyer_id: string;
  seller_id: string;
  state: string;
  attempt: number;
  reference_micro: number;
  agreed: { price_micro: number; quantity: number };
  escrow_micro: number;
  metering?: { cpu_s: number; checksum: string; worker_id: string; wall_ms: number };
  sla?: { deadline: string; breached: boolean };
  settlement?: { price_micro: number; fee_micro: number; penalty_micro: number };
  failure?: { code: string; message: string };
  guardrail?: { passed: boolean; failed: string[] };
  selection?: { provider_name: string; quote_micro: number; reputation_score: number; sample_size: number; verification_rate: number; reason: string };
  verification?: { passed: boolean; level: string; checks: { name: string; passed: boolean }[]; checked_at: string };
  dispute_id?: string;
  links?: { rerouted_from?: string | null; rerouted_to?: string | null };
  created_at: string;
}

export interface ExecutionEvidence {
  id: string;
  trade_id: string;
  worker_id: string;
  job_type: string;
  input_digest: string;
  output_digest: string;
  runtime_version: string;
  started_at?: string;
  completed_at?: string;
  cpu_seconds: number;
  wall_ms: number;
  verification_level: string;
}

export interface Dispute {
  id: string;
  trade_id: string;
  amount_micro: number;
  reason: string;
  state: string;
  outcome?: string;
  note?: string;
}

export interface HackathonReadiness {
  ready: boolean;
  checks: Record<string, boolean>;
  invalid_receivers: { id: string; name: string }[];
  trade_count: number;
  evidence_count: number;
  next_actions: string[];
}

export interface LedgerEntry {
  id: string;
  txn_id: string;
  account: string;
  agent_id: string | null;
  amount_micro: number;
  ref: { type: string; id: string };
  memo: string;
  posted_at: string;
}

export interface PayoutItem {
  id: string;
  settlement_id: string;
  agent_id: string;
  amount_micro: number;
  state: string;
  paypal_item_id: string;
  receiver: string;
  failure?: { code: string; message: string };
}

export interface Approval {
  id: string;
  kind: string;
  subject: { type: string; id: string };
  amount_micro: number;
  state: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  created_at: string;
  expires_at: string;
  facts: Record<string, unknown>;
}

export interface InvariantReport {
  ok: boolean;
  sum_micro: number;
  transactions: number;
  unbalanced_txns: string[];
  negative_wallets: unknown[];
  checked_at: string;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: { type: string; id: string };
  action: string;
  subject: { type: string; id: string };
  severity: string;
}

export interface StreamEvent {
  id: string;
  seq: number;
  type: string;
  trade_id: string | null;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
}

const TOKEN_KEY = "aeon.token";
const ROLE_KEY = "aeon.role";
const QUOTAS_KEY = "aeon.quotas";
const REQUEST_TIMEOUT_MS = 15000;

/**
 * Empty when the console is served by the API (same origin, the default).
 * Set VITE_API_BASE to the API origin when hosting the console separately.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem(QUOTAS_KEY);
  }
}

export function setAuthState(role: Role, quotas: { scenarios_left: number }): void {
  localStorage.setItem(ROLE_KEY, role);
  localStorage.setItem(QUOTAS_KEY, JSON.stringify(quotas));
}

export function getAuthState(): { role: Role; quotas: { scenarios_left: number } } | null {
  const role = localStorage.getItem(ROLE_KEY);
  const quotas = localStorage.getItem(QUOTAS_KEY);
  if ((role !== "operator" && role !== "judge") || !quotas) return null;
  try {
    return { role, quotas: JSON.parse(quotas) };
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  idempotent = false,
  authenticated = true,
): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const token = authenticated ? getToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (idempotent) {
    headers.set("Idempotency-Key", crypto.randomUUID().replace(/-/g, ""));
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? controller.signal,
    });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail ?? body);
    throw new ApiError(response.status, message);
  }
  return body as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "Request timed out. Check that the API server is running.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const api = {
  config: () => request<PublicConfig>("/api/v1/config", {}, false, false),
  login: (email: string, password: string) =>
    request<{ token: string; role: Role; quotas: { scenarios_left: number }; email?: string }>("/api/v1/session/login", {
      method: "POST",
      body: JSON.stringify({ email: email || null, password }),
    }, false, false),
  signup: (email: string, password: string) =>
    request<{ token: string; role: Role; quotas: { scenarios_left: number }; email?: string }>("/api/v1/session/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, false, false),
  judge: () =>
    request<{ token: string; role: Role; quotas: { scenarios_left: number } }>(
      "/api/v1/session/judge",
      { method: "POST", body: JSON.stringify({}) }, false, false,
    ),
  me: () => request<{ role: Role; quotas: { scenarios_left: number } }>("/api/v1/session/me"),
  status: () =>
    request<{
      kill_switch: { active: boolean; reason?: string; updated_at?: string };
      paypal_mode: string;
      llm_mode: string;
      environment: string;
      disclosures: string[];
      approval_threshold_micro: number;
      payout_min_micro: number;
      treasury_reserve_micro: number;
    }>("/api/v1/control/status"),
  agents: () => request<{ agents: Agent[] }>("/api/v1/agents"),
  trades: (limit = 60) => request<{ trades: Trade[] }>(`/api/v1/trades?limit=${limit}`),
  trade: (id: string) => request<Trade & { negotiation_transcript: any[] }>(`/api/v1/trades/${id}`),
  evidence: (id: string) => request<{ evidence: ExecutionEvidence; verification: Trade["verification"] }>(`/api/v1/trades/${id}/evidence`),
  readiness: () => request<HackathonReadiness>("/api/v1/hackathon/readiness"),
  dispute: (id: string) => request<Dispute | null>(`/api/v1/trades/${id}/dispute`),
  createDispute: (id: string, reason: string) =>
    request<Dispute>(`/api/v1/trades/${id}/dispute`, { method: "POST", body: JSON.stringify({ reason }) }, true),
  resolveDispute: (id: string, outcome: "refund" | "release", note: string) =>
    request<Dispute>(`/api/v1/trades/${id}/dispute/resolve`, { method: "POST", body: JSON.stringify({ outcome, note }) }, true),
  entries: (limit = 200) => request<{ entries: LedgerEntry[] }>(`/api/v1/ledger/entries?limit=${limit}`),
  invariant: () => request<InvariantReport>("/api/v1/ledger/invariant"),
  balances: () =>
    request<{ agents: { agent_id: string }[]; system_accounts: Record<string, number>; treasury_float_micro: number }>(
      "/api/v1/ledger/balances",
    ),
  payouts: () => request<{ payouts: PayoutItem[] }>("/api/v1/payouts?limit=100"),
  batches: () => request<{ settlements: any[] }>("/api/v1/settlement/batches"),
  approvals: () => request<{ approvals: Approval[] }>("/api/v1/approvals"),
  decide: (id: string, decision: "APPROVED" | "REJECTED", reason = "") =>
    request(`/api/v1/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }, true),
  audit: (limit = 100) => request<{ audit: AuditEntry[] }>(`/api/v1/audit?limit=${limit}`),
  funding: () => request<{ funding: any[] }>("/api/v1/funding"),
  createFunding: (agentId: string, amountMicro: number) =>
    request<any>("/api/v1/funding", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, amount_micro: amountMicro }),
    }, true),
  captureFunding: (id: string) =>
    request<any>(`/api/v1/funding/${id}/capture`, { method: "POST", body: "{}" }, true),
  runTrade: (buyerId: string, job: { type: string; size: number; params: Record<string, unknown>; deadline_s: number }, sellerId?: string) =>
    request<Trade>("/api/v1/trades", {
      method: "POST",
      body: JSON.stringify({ buyer_id: buyerId, seller_id: sellerId ?? null, job }),
    }, true),
  settlement: () =>
    request<any>("/api/v1/settlement/run", { method: "POST", body: JSON.stringify({ has_approval: false }) }, true),
  scenario: (name: string) =>
    request<any>(`/api/v1/scenarios/${name}/run`, { method: "POST", body: JSON.stringify({}) }, true),
  negotiation: (tradeId: string) =>
    request<{ rounds: any[] }>(`/api/v1/trades/${tradeId}/negotiation`),
  killSwitch: (active: boolean, reason: string) =>
    request("/api/v1/control/kill-switch", {
      method: "POST",
      body: JSON.stringify({ active, reason }),
    }, true),
  pause: (agentId: string) => request(`/api/v1/agents/${agentId}/pause`, { method: "POST", body: "{}" }, true),
  resume: (agentId: string) => request(`/api/v1/agents/${agentId}/resume`, { method: "POST", body: "{}" }, true),
  workers: () => request<{ workers: any[] }>("/api/v1/workers/health"),
  recentEvents: (since = 0) => request<{ events: StreamEvent[] }>(`/api/v1/events/recent?since=${since}`),
  treasurerPlan: () =>
    request<{
      totals: { items: number; amount_micro: number };
      treasury_float_micro: number;
      positions: { agent_id: string; amount_micro: number }[];
      treasurer: { recommend: boolean; note: string; llm: { source: string; model: string }; guardrail?: { passed: boolean; failed: string[] } };
    }>("/api/v1/treasurer/plan"),
  mcpTools: () => request<{ tools: { name: string; description: string }[] }>("/api/v1/mcp/tools"),
  resetDemo: () => request("/api/v1/demo/reset", { method: "POST", body: "{}" }, true),
};

export function streamUrl(): string {
  const token = getToken() ?? "";
  return `${API_BASE}/api/v1/events/stream?token=${encodeURIComponent(token)}`;
}

/** micro-USD -> display string. Money is never computed in floats. */
export function formatMoney(micro: number, withSymbol = true): string {
  const negative = micro < 0;
  const abs = Math.abs(Math.trunc(micro));
  const whole = Math.floor(abs / 1_000_000);
  const fraction = abs % 1_000_000;
  const body = `${whole}.${fraction.toString().padStart(6, "0")}`;
  return `${negative ? "-" : ""}${withSymbol ? "$" : ""}${body}`;
}

export function compactMoney(micro: number): string {
  const abs = Math.abs(micro);
  if (abs >= 1_000_000) return `${(micro / 1_000_000).toFixed(3)}`;
  if (abs >= 1000) return `${(micro / 1000).toFixed(1)}k`;
  return `${micro}`;
}

export function formatTime(iso: string | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
