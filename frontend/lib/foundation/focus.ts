const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true",
  );
}

export function focusFirst(container: HTMLElement): void {
  const [first] = getFocusableElements(container);
  first?.focus();
}

export function trapFocus(container: HTMLElement, event: KeyboardEvent): void {
  if (event.key !== "Tab") {
    return;
  }

  const focusable = getFocusableElements(container);
  if (!focusable.length) {
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement as HTMLElement | null;

  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
    return;
  }

  if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
}

export function createFocusRestorePoint(): () => void {
  const active = document.activeElement as HTMLElement | null;
  return () => {
    active?.focus();
  };
}
