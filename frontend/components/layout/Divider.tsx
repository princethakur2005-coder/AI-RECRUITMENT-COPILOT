import type { CSSProperties, HTMLAttributes } from "react";

import "./layout.css";
import { cx, type SpaceToken, spaceVar } from "./utils";

export interface DividerProps extends Omit<HTMLAttributes<HTMLHRElement>, "size"> {
  orientation?: "horizontal" | "vertical";
  marginY?: SpaceToken;
  marginX?: SpaceToken;
}

export function Divider({
  className,
  style,
  orientation = "horizontal",
  marginY = "4",
  marginX,
  ...props
}: DividerProps) {
  const mergedStyle: CSSProperties = {
    ...style,
    marginTop: orientation === "horizontal" ? spaceVar(marginY) : undefined,
    marginBottom: orientation === "horizontal" ? spaceVar(marginY) : undefined,
    marginLeft: orientation === "vertical" ? spaceVar(marginX ?? "4") : undefined,
    marginRight: orientation === "vertical" ? spaceVar(marginX ?? "4") : undefined,
  };

  return <hr {...props} className={cx("layout-divider", className)} data-orientation={orientation} style={mergedStyle} />;
}
