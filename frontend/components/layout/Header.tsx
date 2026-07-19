import type { HTMLAttributes, ReactNode } from "react";


import { cx } from "./utils";

export interface HeaderProps extends HTMLAttributes<HTMLElement> {
  left?: ReactNode;
  right?: ReactNode;
  sticky?: boolean;
}

export function Header({ className, left, right, sticky = true, children, ...props }: HeaderProps) {
  return (
    <header {...props} className={cx(sticky ? "layout-header" : undefined, className)}>
      <div className="layout-header-inner">
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", minWidth: 0 }}>{left ?? children}</div>
        {right ? <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>{right}</div> : null}
      </div>
    </header>
  );
}
