import { createContext, useContext } from "react";
import type { HTMLAttributes, ReactNode } from "react";


import { cx, useControllableState, useStableId } from "./utils";

interface TabsContextValue {
  value: string;
  setValue: (next: string) => void;
  baseId: string;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("Tabs components must be used within Tabs.Root");
  }
  return context;
}

export interface TabsRootProps {
  value?: string;
  defaultValue: string;
  onValueChange?: (next: string) => void;
  children?: ReactNode;
  className?: string;
}

function TabsRoot({ value, defaultValue, onValueChange, children, className }: TabsRootProps) {
  const [current, setCurrent] = useControllableState<string>({
    value,
    defaultValue,
    onChange: onValueChange,
  });
  const baseId = useStableId("tabs");

  return (
    <TabsContext.Provider value={{ value: current, setValue: setCurrent, baseId }}>
      <div className={cx("surface-root surface-tabs", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

export interface TabsListProps extends HTMLAttributes<HTMLDivElement> {}

function TabsList(props: TabsListProps) {
  return <div {...props} role="tablist" className={cx("surface-tab-list", props.className)} />;
}

export interface TabsTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  value: string;
}

function TabsTrigger({ value, className, children, ...props }: TabsTriggerProps) {
  const { value: active, setValue, baseId } = useTabsContext();
  const selected = active === value;
  const tabId = `${baseId}-tab-${value}`;
  const panelId = `${baseId}-panel-${value}`;

  return (
    <button
      {...props}
      id={tabId}
      role="tab"
      type="button"
      aria-selected={selected}
      aria-controls={panelId}
      data-active={selected}
      className={cx("surface-tab-trigger surface-focus-ring", className)}
      onClick={(event) => {
        props.onClick?.(event);
        if (!event.defaultPrevented) {
          setValue(value);
        }
      }}
    >
      {children}
    </button>
  );
}

export interface TabsPanelProps extends HTMLAttributes<HTMLDivElement> {
  value: string;
}

function TabsPanel({ value, className, children, ...props }: TabsPanelProps) {
  const { value: active, baseId } = useTabsContext();
  const selected = active === value;
  const tabId = `${baseId}-tab-${value}`;
  const panelId = `${baseId}-panel-${value}`;

  if (!selected) {
    return null;
  }

  return (
    <div
      {...props}
      id={panelId}
      role="tabpanel"
      aria-labelledby={tabId}
      className={cx("surface-tab-panel", className)}
    >
      {children}
    </div>
  );
}

export const Tabs = {
  Root: TabsRoot,
  List: TabsList,
  Trigger: TabsTrigger,
  Panel: TabsPanel,
};
