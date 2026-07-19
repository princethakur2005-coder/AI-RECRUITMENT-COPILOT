import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";


import type { UISize } from "./types";
import { cx } from "./utils";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: UISize;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", leftIcon, rightIcon, children, type = "button", ...props },
  ref,
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      className={cx("ui-btn ui-focus-ring", `ui-btn-${size}`, `ui-btn-${variant}`, className)}
    >
      {leftIcon}
      <span>{children}</span>
      {rightIcon}
    </button>
  );
});
