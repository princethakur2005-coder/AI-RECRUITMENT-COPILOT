import type { HTMLAttributes } from "react";

import { Button } from "../core/Button";
import { cx } from "../core/utils";


export interface PaginationProps extends HTMLAttributes<HTMLElement> {
  page: number;
  pageSize: number;
  total: number;
  onPageChange?: (nextPage: number) => void;
  showPageButtons?: boolean;
  siblingCount?: number;
}

function range(start: number, end: number): number[] {
  const output: number[] = [];
  for (let i = start; i <= end; i += 1) {
    output.push(i);
  }
  return output;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  showPageButtons = true,
  siblingCount = 1,
  className,
  ...props
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
  const currentPage = Math.min(Math.max(page, 1), totalPages);

  const startPage = Math.max(1, currentPage - siblingCount);
  const endPage = Math.min(totalPages, currentPage + siblingCount);
  const pages = range(startPage, endPage);

  return (
    <nav {...props} className={cx("dd-root dd-pagination", className)} aria-label="Pagination">
      <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)" }}>
        Page {currentPage} of {totalPages}
      </div>
      <div className="dd-pagination-pages">
        <Button size="sm" variant="secondary" disabled={currentPage <= 1} onClick={() => onPageChange?.(currentPage - 1)}>
          Previous
        </Button>
        {showPageButtons
          ? pages.map((p) => (
              <Button
                key={p}
                size="sm"
                variant={p === currentPage ? "primary" : "ghost"}
                aria-current={p === currentPage ? "page" : undefined}
                onClick={() => onPageChange?.(p)}
              >
                {p}
              </Button>
            ))
          : null}
        <Button size="sm" variant="secondary" disabled={currentPage >= totalPages} onClick={() => onPageChange?.(currentPage + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}
