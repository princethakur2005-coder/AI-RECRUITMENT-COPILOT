import type { CSSProperties } from "react";

export const visuallyHiddenStyle: CSSProperties = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

export function createAriaDescriptionIds(...ids: Array<string | undefined | null>): string | undefined {
  const value = ids.filter(Boolean).join(" ");
  return value || undefined;
}

export function isHTMLElement(target: EventTarget | null): target is HTMLElement {
  return target instanceof HTMLElement;
}

export function makeLiveRegionProps(mode: "polite" | "assertive" = "polite") {
  return {
    role: "status",
    "aria-live": mode,
  } as const;
}
