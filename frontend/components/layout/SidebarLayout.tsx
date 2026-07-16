import type { HTMLAttributes, ReactNode } from "react";

import "./layout.css";
import { cx } from "./utils";

export interface SidebarLayoutProps extends HTMLAttributes<HTMLElement> {
  children?: ReactNode;
  sticky?: boolean;
}

export function SidebarLayout({ children, className, sticky = false, ...props }: SidebarLayoutProps) {
  return (
    <aside {...props} className={cx("layout-sidebar", className)} data-sticky={sticky}>
      {children}
    </aside>
  );
}
