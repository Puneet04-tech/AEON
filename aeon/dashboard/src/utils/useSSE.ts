import create from "zustand";

interface SSEEvent {
  id: number;
  type: "info" | "success" | "warning" | "error";
  message: string;
  agent?: string;
  timestamp: number;
}

interface SSEStore {
  connected: boolean;
  events: SSEEvent[];
  connect: () => void;
  disconnect: () => void;
  addEvent: (event: Omit<SSEEvent, "id" | "timestamp">) => void;
}

export const useSSE = create<SSEStore>((set) => ({
  connected: false,
  events: [],
  connect: () => set({ connected: true }),
  disconnect: () => set({ connected: false }),
  addEvent: (event) =>
    set((state) => {
      const newEvent = {
        id: state.events.length + 1,
        timestamp: Date.now(),
        ...event,
      };
      return {
        connected: true,
        events: [newEvent, ...state.events].slice(0, 100),
      };
    }),
}));