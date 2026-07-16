import type { ImgHTMLAttributes } from "react";

import "./core-ui.css";
import type { UISize } from "./types";
import { cx, getInitials } from "./utils";

export interface AvatarProps {
  src?: string;
  alt?: string;
  name?: string;
  size?: UISize;
  imgProps?: Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt">;
  className?: string;
}

export function Avatar({ src, alt, name, size = "md", imgProps, className }: AvatarProps) {
  const resolvedAlt = alt ?? name ?? "Avatar";

  return (
    <span className={cx("ui-avatar ui-root", `ui-avatar-${size}`, className)} aria-label={resolvedAlt} role="img">
      {src ? (
        <img {...imgProps} src={src} alt={resolvedAlt} />
      ) : (
        <span className="ui-avatar-fallback" aria-hidden="true">
          {getInitials(name)}
        </span>
      )}
    </span>
  );
}
