# AEON Premium Design System: Rose Liquid Glass & Neumorphic Architecture

This document establishes the official user interface specification, design tokens, component architecture, and structural layout for **Project AEON (Agent-to-Agent Settlement Network)**. It serves as a strict blueprint for front-end implementation to completely eliminate AI-generated "slop aesthetics" (such as harsh neon borders, generic card grids, decorative illustrations, and uncalibrated saturated gradients).

The aesthetic direction is a highly disciplined, hyper-dense **operations control center**. It combines the volumetric softness of light-handed neumorphism with the sophisticated depth of an organic, fluid rose glass overlay—optimized for data visualization and precision human-in-the-loop oversight.

---

## 1. Global Architectural Principles & Tokens

### 1.1 Color Systems (Calibrated, Non-Saturated)
To maintain absolute professional credibility for a system processing money, colors are strictly functional, never decorative. Pure absolute white (`#FFFFFF`) and deep black (`#000000`) are banned to eliminate eye strain and mechanical AI signatures.

```css
:root {
  /* Dynamic Palette: Light Theme Default */
  --theme-transition: background-color 300ms cubic-bezier(0.4, 0, 0.2, 1), 
                      box-shadow 300ms cubic-bezier(0.4, 0, 0.2, 1);

  /* Neutrals: 9-Step Calibrated Cool Slate Grid */
  --neutral-bg: #F4F6F8;          /* Base floor (soft off-white) */
  --neutral-surface: #EBF0F5;     /* Neumorphic base layer */
  --neutral-surface-2: #E1E7EE;   /* Inset container / Hover state */
  --neutral-border: #D7DEE6;      /* Low-contrast hairline */
  --neutral-border-strong: #C5CDD7;/* Structural divide */
  --neutral-text-min: #7E8B9B;    /* Captions, disabled fields */
  --neutral-text-mid: #4A5564;    /* Secondary text, active labels */
  --neutral-text: #2C3540;        /* Body, high readability text */
  --neutral-text-max: #181E26;    /* Headings, structural values */

  /* The Signature Accent: Rose Liquid Glass Engine */
  --rose-glass-tint: rgba(244, 63, 94, 0.04);
  --rose-glass-glow: rgba(251, 113, 133, 0.15);
  --accent-solid: #E11D48;        /* Rose-700 for deterministic active highlights */
  --accent-focus: rgba(225, 29, 72, 0.12);

  /* Semantic Money & Security Matrix (Paired with Icons) */
  --semantic-in: #0D9488;          /* Money-in/Teal: Real captured cash */
  --semantic-out: #D97706;         /* Money-out/Amber: Payouts/Disbursements */
  --semantic-risk: #E11D48;        /* Danger/Rose: SLA Breaches, Attacks */
  --semantic-pending: #4B5563;     /* Systemic processing state */

  /* Neumorphic Shadow Structs (Formed via Ambient Contrast) */
  --shadow-raised: -4px -4px 9px rgba(255, 255, 255, 0.9), 
                    4px 4px 9px rgba(166, 180, 200, 0.45);
  --shadow-inset: inset -2px -2px 5px rgba(255, 255, 255, 0.8), 
                   inset 2px 2px 5px rgba(166, 180, 200, 0.5);
  --shadow-overlay: 0px 12px 32px rgba(24, 30, 38, 0.08);
}

[data-theme='dark'] {
  /* Neutrals: 9-Step Calibrated Deep Charcoal Grid */
  --neutral-bg: #121519;          /* Deep base floor */
  --neutral-surface: #1A1E24;     /* Dark neumorphic base */
  --neutral-surface-2: #222831;   /* Inset container / Hover state */
  --neutral-border: #2D3541;      /* Low-contrast dark hairline */
  --neutral-border-strong: #3F4A5B;/* Structural divide */
  --neutral-text-min: #627288;    /* Captions, muted logs */
  --neutral-text-mid: #94A6BF;    /* Secondary metadata */
  --neutral-text: #D2DCEC;        /* High-contrast body text */
  --neutral-text-max: #F1F5F9;    /* Crisp emission header values */

  /* Rose Liquid Glass Engine (Dark Shifted) */
  --rose-glass-tint: rgba(251, 113, 133, 0.02);
  --rose-glass-glow: rgba(244, 63, 94, 0.25);
  --accent-solid: #FB7185;
  --accent-focus: rgba(251, 113, 133, 0.15);

  /* Dark Shadows (Absorptive Neumorphism) */
  --shadow-raised: -3px -3px 7px rgba(38, 45, 56, 0.4), 
                    3px 3px 7px rgba(5, 6, 8, 0.7);
  --shadow-inset: inset -2px -2px 5px rgba(38, 45, 56, 0.3), 
                   inset 2px 2px 5px rgba(5, 6, 8, 0.6);
  --shadow-overlay: 0px 16px 40px rgba(0, 0, 0, 0.5);
}
```

### 1.2 Typography & Spacing Scale
*   **Font Families:** Self-hosted `IBM Plex Sans` for interface operations; `IBM Plex Mono` featuring tabular numerals (`font-variant-numeric: tabular-nums`) for absolute mathematical alignment across ledgers, hashes, amounts, and audit timestamps.
*   **Type Scale:** 11px (Micro captions) → 12px (Grid text) → 13px (Base standard) → 15px (Sub-headings) → 18px (Section titles) → 24px (System Critical KPIs).
*   **Spacing Grid:** Strict 4px base increment system (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`).
*   **Radii:** 2px for operational inputs/chips; 4px for primary functional dashboard panels. 

---

## 2. Core Global Layout Architecture

The viewport is locked to `100vh` / `100vw` with zero overflow allowed on the root body. The interface uses a three rigid zones layout:

```
+--------------------------------------------------------------------------------------------------+
| Environment Bar: [Environment: PayPal Sandbox] | Invariant: 0.000000 uUSD | Kill Switch: ACTIVE |
+---+------------------------------------------------------------------------------------------+
| L | Top Zone: Interactive Node Graph (React Flow)                                                |
| E | - Live Visual Nodes: Consumer, Provider, Lender, Treasurer Agents                            |
| F | - Flow Lines: Animated edges streaming transactions dynamically                              |
| T |                                                                                              |
|   +------------------------------------------------------------------------+---------------------+
| R | Bottom Zone: Unified AG Grid Console Data Layer                        | RIGHT DRAWER (360px)|
| A | [Ledger] [Trades] [Payouts] [Agents] [Approvals] [Audit]               | - Real-time SSE Log |
| I |                                                                        | - Master-Detail     |
| L | - Dense, non-zebra tabular view                                        |   Negotiation Loop  |
|   | - Tabular numerical financial rows                                     |   Transcript Box    |
+---+------------------------------------------------------------------------+---------------------+
```

---

## 3. Component & Page Blueprints

### Component Document 1: System Top Bar & Environment Controller

#### 1. Design Specification
A thin, 36px static horizontal line fixed to the top viewport ceiling. It establishes security boundaries, application privileges, and immediate human override access.

```
[❖ AEON System]  [Role: OPERATOR]  [Env: PAYPAL SANDBOX] ------ [LEDGER INVARIANT: 0 uUSD ✓] -- [[ EMERGENCY KILL SWITCH ]]
```

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Surface:** Flat `--neutral-surface` backed by a `border-bottom: 1px solid var(--neutral-border-strong)`.
*   **Ledger Invariant Status Chip:** Inset style (`box-shadow: var(--shadow-inset)`). If the invariant calculation equals exactly `0`, the chip renders a micro `2px` border-left of `--semantic-in`.
*   **Emergency Kill Switch Button:** Modeled as a physical, heavy convex button with high structural resistance (`box-shadow: var(--shadow-raised)`). It is coated in a volatile deep rose fluid translucent sheen: `background: linear-gradient(135deg, rgba(225,29,72,0.1), var(--rose-glass-tint))`.

#### 3. State Matrix
*   **Default Operation:** Text labels crisp, Kill Switch inactive with a dormant dark red indicator dot.
*   **Kill Switch Hover:** `box-shadow: var(--shadow-inset); background: rgba(225, 29, 72, 0.2); transition: var(--theme-transition);`.
*   **System Engaged / Triggered:** Entire Top Bar shifts ambient flash loops to a soft dark crimson back-tint. The switch turns into a locked down concave state, pulsating a raw `--semantic-risk` beacon (`180ms ease-out`).

#### 4. Accessibility Compliance
*   **Interactive Target:** Kill switch click area forces a minimum metric block of `28px x 140px` (exceeding the standard `24px` density metric).
*   **ARIA Attributes:** `aria-label="Global Emergency System Kill Switch"`, `aria-live="assertive"`, `aria-checked="false"`.

---

### Component Document 2: Active Agent Topology Matrix (React Flow Canvas)

#### 1. Design Specification
Occupies the top resizable half of the screen workspace. It renders live custom structural nodes representing registered runtime entities: *Consumers, Providers, Treasurers,* and *Lenders*.

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Canvas Base:** Set to `--neutral-surface`. The grid grid-lines use a micro-dot layout via custom SVG patterns using `--neutral-border`.
*   **Custom Node Panels:** Styled as floating glass panes with structural weight.
    ```css
    .aeon-node-pane {
      background: rgba(235, 240, 245, 0.6);
      backdrop-filter: blur(12px) saturate(110%);
      border: 1px solid rgba(255, 255, 255, 0.4);
      box-shadow: var(--shadow-raised);
    }
    ```
*   **Edge Data Routing:** Connections between nodes use non-bezier straight or step lines. Dynamic financial operations trigger real-time animated dashes traveling down the edge path towards the receiving node. Money-in uses `--semantic-in` dashes; payouts use `--semantic-out` dashes.

#### 3. State Matrix
*   **Node Active State:** Standard configuration. Displays a `11px IBM Plex Mono` balance counter.
*   **Node Selected State:** Applies an explicit sharp border focus ring (`1px solid var(--accent-solid)`) and projects a faint underlying signature rose ambient blur overlay (`box-shadow: 0 0 12px var(--rose-glass-glow)`).
*   **Node Suspended / Faulted State:** (`FR-10: SLA Penalty / Workers failing health checks`). Node background switches opacity dynamically, showing a solid `--semantic-risk` left structural border block indicator. The internal text labels drop visibility to `--neutral-text-min`.

#### 4. Accessibility Compliance
*   Keyboard navigation allows focus shifting across nodes using `Tab` keys.
*   `aria-roledescription="Network Topology Graph Overview Map"`.
*   Supports full `prefers-reduced-motion` detection: when active, edge line animations instantly freeze to solid color states.

---

### Component Document 3: Deep-Data Console Ledger Layer (AG Grid Engine)

#### 1. Design Specification
The system's core component. It handles massive multi-column arrays across tabs: *Ledger entries, Trades, Payout items, Agent registries, Approvals queue, Security audit logs*.

```
[ Ledger Entries ] [ Active Trades ] [ PayPal Payout Batches ] [ Operational Approvals ]
----------------------------------------------------------------------------------------
TXN ID      TIMESTAMP             ACCOUNT             DEBIT (uUSD)        CREDIT (uUSD)
----------------------------------------------------------------------------------------
01JTXN1     2026-11-01 10:15:03   agent_available          516,000                   0
01JTXN1     2026-11-01 10:15:03   agent_escrow                   0             516,000
```

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Console Framework:** Inset box layout (`box-shadow: var(--shadow-inset)`) surrounding the tab menu bar.
*   **AG Grid Theme Architecture Override:**
    *   `Zebra-striping`: **Strictly Disabled** to prevent visual noise.
    *   `Headers`: Flat `--neutral-surface-2`, text `font-weight: 600`, strict `1px` base separation lines.
    *   `Row Height`: Compact 24px layout maximizing visible structural metrics.
    *   `Row Selection`: Background highlighted with a distinct `--neutral-surface-2` frame, paired with an `8% opacity accent-solid` fill mask overlay.
*   **Cell Render Blocks:** Money values use `IBM Plex Mono`, right-aligned text formatting, and tabular layout configuration. Positive cash volumes apply `--semantic-in` color codes; outward distributions use `--semantic-out`.

#### 3. State Matrix
*   **Data Cell Hover:** Displays an accelerated focus backdrop transition (`background-color: var(--neutral-surface-2); duration: 120ms`).
*   **Pending Operational Row Resolution:** (e.g., Payout state `SUBMITTED`). Renders a trailing system-state tracking text flag, set to `--semantic-pending` parameters.
*   **Data Violation / Alert Row Event:** Emits an immediate high-visibility security color alert background line, utilizing a solid `--semantic-risk` indicator label strip.

#### 4. Accessibility Compliance
*   Grid implements full standard `WAI-ARIA` keyboard grids controls (`Home`, `End`, arrow keys navigation).
*   `role="grid"`, `aria-colcount`, `aria-rowcount`. All numeric columns map explicit headers to data cells via `aria-describedby`.

---

### Component Document 4: Human-in-the-Loop Approval Panel

#### 1. Design Specification
A specialized UI component housed inside the central AG Grid workspace console or as an overlay sheet. It intercepts financial transactions that cross security thresholds (e.g., payouts > $25.00 USD).

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Container Shell:** Renders as a convex plate (`box-shadow: var(--shadow-raised)`) covered by a smooth rose liquid glass glaze layer (`backdrop-filter: blur(16px)`).
*   **Risk Metrics Display Block:** Embeds clear mathematical delta summaries within inset fields (`box-shadow: var(--shadow-inset)`), showing automated risk evaluation metadata alongside raw transaction numbers.

#### 3. State Matrix
*   **Action Awaiting Resolution:** The confirmation action control fields maintain standard interaction states. The "Reject" button requires typing the associated Agent Registry reference name to confirm destruction.
*   **Execution: Approved State:** Upon user activation, the component triggers a quick flash transition (`140ms ease-out`), updating all dependent records immediately.
*   **Execution: Rejected State:** Intercepts the workflow pipeline, returns the escrow assets, marks the batch index fields closed, and writes a warning record directly to the security audit stream.

#### 4. Accessibility Compliance
*   Defines explicit focus capture loops when rendered as a modal overlay, blocking tab-escape vectors.
*   `aria-modal="true"`, `role="alertdialog"`. Emits localized audible live updates via dedicated screen reader attributes (`aria-live="assertive"`).

---

### Component Document 5: Autonomous Agent Negotiation & SSE Log Drawer

#### 1. Design Specification
A fixed 360px vertical utility container locked to the right side of the dashboard footprint. The top section presents real-time structured communication transcripts between buyer and seller models. The bottom section processes a live stream of JSON system events via Server-Sent Events (SSE).

```
=== LIVE AGENT NEGOTIATION TRANSCRIPT ===
[Round 1/3] ATLAS -> BOREALIS
├─ Offer: 0.040 uUSD/cpu_sec
└─ Reasoning: "Worker load high. S1 profile path."

[Round 2/3] BOREALIS -> ATLAS
├─ Counter: 0.046 uUSD/cpu_sec
└─ Reasoning: "Energy surges detected via weather data."

[Round 3/3] ATLAS -> BOREALIS [AGREED ✓]
└─ Final: 0.043 uUSD/cpu_sec
   └─ Guardrail: PASSED
```

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Drawer Structure:** Framed as an isolated vertical section featuring a robust border block (`border-left: 1px solid var(--neutral-border-strong)`).
*   **Transcript Interaction Blocks:** Step histories wrap inside deep-set text rows (`box-shadow: var(--shadow-inset)`). 
*   **Liquid Sheen Alert Indicators:** Real-time log tracking markers use precise status dots paired with micro-text labels, utilizing a `120ms fade-in` animation loop when new events are added to the layout.

#### 3. State Matrix
*   **Standard Log Ingest:** Automated line-by-line scrolling stack updates. Numbers and code outputs use `IBM Plex Mono`.
*   **Guardrail Violation Interception Event:** The transaction block turns solid red (`--semantic-risk`), accompanied by an explanatory text detail box provided by the automated validation layer.
*   **Network Loss / Reconnecting State:** Instantly shifts the stream layout view to an amber hue (`--semantic-out`), maintaining visible status lines until connection recovery is confirmed.

#### 4. Accessibility Compliance
*   `role="log"`, `aria-live="polite"`. The log stream viewport provides an operational freeze toggle via `Spacebar`, stopping auto-scrolling behaviors so keyboard users can navigate individual records safely.

---

### Page Document 1: Primary Operator Command Console Workspace

#### 1. Design Specification
The single-page operational hub for Project AEON. It coordinates the Top Bar environment elements, the top React Flow active topology canvas, and the bottom AG Grid ledger tracking tabs into one unified screen workspace.

#### 2. Layout Structure & Code Setup
```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <title>AEON // Agent-to-Agent Settlement Control Console</title>
  <link rel="stylesheet" href="tokens.css">
  <style>
    body {
      margin: 0; padding: 0;
      width: 100vw; height: 100vh;
      background-color: var(--neutral-bg);
      color: var(--neutral-text);
      font-family: 'IBM Plex Sans', sans-serif;
      overflow: hidden;
    }
    .aeon-workspace-grid {
      display: grid;
      grid-template-columns: 56px 1fr 360px;
      grid-template-rows: 36px 1fr;
      width: 100%; height: 100%;
    }
    .sys-top-bar {
      grid-column: 1 / -1;
      height: 36px;
      background-color: var(--neutral-surface);
      border-bottom: 1px solid var(--neutral-border-strong);
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 12px; box-sizing: border-box;
    }
    .left-rail-navigation {
      grid-column: 1;
      background-color: var(--neutral-surface);
      border-right: 1px solid var(--neutral-border-strong);
      display: flex; flex-direction: column; align-items: center; padding-top: 12px;
    }
    .main-operation-theater {
      grid-column: 2;
      display: grid;
      grid-template-rows: 4fr 5fr; /* Dynamic Split Canvas to Grid Ratio */
      border-right: 1px solid var(--neutral-border-strong);
      background-color: var(--neutral-bg);
    }
    .topology-canvas-pane {
      background: var(--neutral-surface);
      position: relative;
      overflow: hidden;
      border-bottom: 1px solid var(--neutral-border-strong);
    }
    .data-grid-tabs-pane {
      padding: 12px;
      background-color: var(--neutral-bg);
      display: flex; flex-direction: column;
    }
    .right-stream-drawer {
      grid-column: 3;
      background-color: var(--neutral-surface);
      display: flex; flex-direction: column;
    }
  </style>
</head>
<body>
  <div class="aeon-workspace-grid">
    <!-- Top System Environment Strip -->
    <header class="sys-top-bar">...</header>
    
    <!-- 56px Control Rail -->
    <nav class="left-rail-navigation">...</nav>
    
    <!-- Central Control Viewport -->
    <main class="main-operation-theater">
      <section class="topology-canvas-pane" id="react-flow-canvas">...</section>
      <section class="data-grid-tabs-pane" id="ag-grid-console">...</section>
    </main>
    
    <!-- Right Telemetry Panel -->
    <aside class="right-stream-drawer">...</aside>
  </div>
</body>
</html>
```

#### 3. Interaction Design & Viewport Responsiveness
*   **Workspace Splitting:** The central divider between the topology canvas and the ledger tab layouts supports structural dragging adjustments, redrawing grid viewports instantly via automated window listener updates.
*   **Resolution Adaptability:** The interface layouts adapt dynamically across target production viewports (`1280px`, `1440px`, and `1920px`), dropping or combining secondary column segments layout cleanly to maintain high text clarity without scaling artifacts.

---

### Page Document 2: Interactive Judge Strategy Sandbox

#### 1. Design Specification
A specialized operational mode activated via the system top bar controller. It injects a highly guided operational control panel directly above the main theater windows, enabling evaluation teams to trigger sequential simulation scenarios (e.g., `S1: Core Compute Loop`, `S2: Fault Ingestion & Bond Slashing`).

#### 2. Neumorphic & Rose Liquid Glass Properties
*   **Sandbox Controller Block:** Formed as a distinct overlay panel featuring convex styling cues (`box-shadow: var(--shadow-raised)`). It sits comfortably behind a protective translucent rose liquid tint film block layer (`background: rgba(235, 240, 245, 0.7); backdrop-filter: blur(8px)`).
*   **Execution Strategy Controls:** Modeled as physical neumorphic toggle options. When a scenario runs, dependent steps update their layout dynamically through an inset active indicator framework (`box-shadow: var(--shadow-inset); border-left: 2px solid var(--accent-solid)`).

#### 3. State Matrix
*   **System Cold Start State:** (`FR-14: Waking Services Mode`). Temporarily disables interactive execution triggers, setting background text variables to low-contrast tones (`--neutral-text-min`) while showing an accurate loading state progress indicator across the screen.
*   **Active Scenario Progression Mode:** Tracks execution paths step by step, updating associated visualization components and populating the data grids without requiring full page refreshes.
*   **Evaluation Quota Exceeded:** Instantly limits further simulation triggers if runtime boundaries are crossed. The control fields switch to locked visibility modes, showing clear informational notices regarding quota constraints.

#### 4. Accessibility Compliance
*   `role="region"`, `aria-label="Judge Scenario Demonstration Controller Panel"`.
*   Includes full keyboard selection loops across individual scenario buttons, allowing evaluation teams to run multi-step tests using simple arrow key and enter commands.
