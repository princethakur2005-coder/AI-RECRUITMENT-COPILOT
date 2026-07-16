import type { ThemeMode } from "./design-tokens";

export type ThemeSubscriber = (theme: ThemeMode) => void;

export interface ThemeProviderOptions {
  storageKey?: string;
  defaultTheme?: ThemeMode;
  documentElement?: HTMLElement;
}

export class ThemeProvider {
  private storageKey: string;
  private defaultTheme: ThemeMode;
  private currentTheme: ThemeMode;
  private subscribers: Set<ThemeSubscriber>;
  private documentElement: HTMLElement | null;

  constructor(options: ThemeProviderOptions = {}) {
    this.storageKey = options.storageKey ?? "app-theme";
    this.defaultTheme = options.defaultTheme ?? "light";
    this.subscribers = new Set<ThemeSubscriber>();
    this.documentElement =
      options.documentElement ??
      (typeof document !== "undefined" ? document.documentElement : null);
    this.currentTheme = this.resolveInitialTheme();
    this.applyTheme(this.currentTheme);
  }

  getTheme(): ThemeMode {
    return this.currentTheme;
  }

  setTheme(theme: ThemeMode): ThemeMode {
    this.currentTheme = theme;
    this.persistTheme(theme);
    this.applyTheme(theme);
    this.notify(theme);
    return theme;
  }

  toggleTheme(): ThemeMode {
    return this.setTheme(this.currentTheme === "dark" ? "light" : "dark");
  }

  subscribe(listener: ThemeSubscriber): () => void {
    this.subscribers.add(listener);
    listener(this.currentTheme);

    return () => {
      this.subscribers.delete(listener);
    };
  }

  private resolveInitialTheme(): ThemeMode {
    const stored = this.readStoredTheme();
    if (stored === "light" || stored === "dark") {
      return stored;
    }

    if (typeof window !== "undefined" && window.matchMedia) {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      return prefersDark ? "dark" : this.defaultTheme;
    }

    return this.defaultTheme;
  }

  private applyTheme(theme: ThemeMode): void {
    if (!this.documentElement) {
      return;
    }
    this.documentElement.setAttribute("data-theme", theme);
  }

  private notify(theme: ThemeMode): void {
    this.subscribers.forEach((listener) => listener(theme));
  }

  private readStoredTheme(): ThemeMode | null {
    if (typeof window === "undefined" || !window.localStorage) {
      return null;
    }

    const value = window.localStorage.getItem(this.storageKey);
    return value === "light" || value === "dark" ? value : null;
  }

  private persistTheme(theme: ThemeMode): void {
    if (typeof window === "undefined" || !window.localStorage) {
      return;
    }

    window.localStorage.setItem(this.storageKey, theme);
  }
}

export const themeProvider = new ThemeProvider();
