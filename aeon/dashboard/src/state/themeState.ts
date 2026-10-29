import create from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  setTheme: (newTheme: Theme) => void;
  toggleTheme: () => void;
}

// Initialize from localStorage or system preference
const getInitialTheme = (): Theme => {
  if (typeof window !== "undefined") {
    const saved = localStorage.getItem("aeon-theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
    // Check system preference
    if ((window as any).matchMedia) {
      const mq = (window as any).matchMedia("(prefers-color-scheme: dark)");
      if (mq.matches) {
        return "dark";
      }
    }
  }
  return "light";
};

export const useTheme = create<ThemeState>((set) => ({
  theme: getInitialTheme(),
  setTheme: (newTheme: Theme) => {
    localStorage.setItem("aeon-theme", newTheme);
    set({ theme: newTheme });
    // Apply to root element
    const root = document.documentElement;
    if (newTheme === "dark") {
      root.setAttribute("data-theme", "dark");
    } else {
      root.removeAttribute("data-theme");
    }
  },
  toggleTheme: () => {
    set((state) => {
      const newTheme: Theme = state.theme === "light" ? "dark" : "light";
      return { theme: newTheme };
    });
  },
}));