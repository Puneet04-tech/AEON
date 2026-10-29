/** Typed API client for the AEON console. */

export type Role = "operator" | "judge";

export interface PublicConfig {
  environment: string;
  paypal_mode: "sandbox" | "mock";
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
  links?: { rerouted_from?: string | null; rerouted_to?: string | null };
  created_at: string;
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

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, idempotent = false): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (idempotent) {
    headers.set("Idempotency-Key", crypto.randomUUID().replace(/-/g, ""));
  }
  const response = await fetch(path, { ...init, headers });
  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail ?? body);
    if (response.status === 401) setToken(null);
    throw new ApiError(response.status, message);
  }
  return body as T;
}

export const api = {
  config: () => request<PublicConfig>("/api/v1/config"),
  login: (password: string) =>
    request<{ token: string; role: Role }>("/api/v1/session/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  judge: () =>
    request<{ token: string; role: Role; quotas: { scenarios_left: number } }>(
      "/api/v1/session/judge",
      { method: "POST", body: JSON.stringify({}) },
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
};

export function streamUrl(): string {
  const token = getToken() ?? "";
  return `/api/v1/events/stream?token=${encodeURIComponent(token)}`;
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
