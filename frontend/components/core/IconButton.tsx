import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";


import type { UISize } from "./types";
import { cx } from "./utils";

export type IconButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: ReactNode;
  label: string;
  variant?: IconButtonVariant;
  size?: UISize;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, icon, label, variant = "ghost", size = "md", type = "button", ...props },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-label={label}
      className={cx("ui-btn ui-icon-btn ui-focus-ring", `ui-btn-${size}`, `ui-btn-${variant}`, className)}
    >
      {icon}
    </button>
  );
});
