import type { HTMLAttributes, ReactNode } from "react";

import { Card, CardBody, CardHeader } from "../surface/Card";
import { cx } from "../core/utils";


export interface AnalyticsWidgetProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  as?: "section" | "article" | "div";
}

export function AnalyticsWidget({
  title,
  description,
  action,
  children,
  className,
  as = "section",
  ...props
}: AnalyticsWidgetProps) {
  return (
    <Card as={as} className={cx("an-root an-widget", className)} {...props}>
      <CardHeader>
        <div className="an-widget-header">
          <div>
            <h3 className="an-widget-title">{title}</h3>
            {description ? <p className="an-widget-description">{description}</p> : null}
          </div>
          {action ? <div>{action}</div> : null}
        </div>
      </CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}
