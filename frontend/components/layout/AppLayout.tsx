import type { CSSProperties, ReactNode } from "react";

import "./layout.css";
import { cx } from "./utils";

export interface AppLayoutProps {
  header?: ReactNode;
  sidebar?: ReactNode;
  children?: ReactNode;
  className?: string;
  contentClassName?: string;
  sidebarWidth?: string;
  style?: CSSProperties;
}

export function AppLayout({
  header,
  sidebar,
  children,
  className,
  contentClassName,
  sidebarWidth = "17.5rem",
  style,
}: AppLayoutProps) {
  return (
    <div className={cx("layout-root layout-app", className)} style={style}>
      {header}
      <div className="layout-shell" data-with-sidebar={Boolean(sidebar)} style={{ ["--layout-sidebar-width" as string]: sidebarWidth }}>
        {sidebar}
        <main className={contentClassName}>{children}</main>
      </div>
    </div>
  );
}
