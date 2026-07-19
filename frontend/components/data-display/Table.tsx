import type { ReactNode, TableHTMLAttributes } from "react";


import { cx } from "../core/utils";

export interface TableColumn<T> {
  key: keyof T | string;
  header: ReactNode;
  width?: string;
  render?: (row: T, rowIndex: number) => ReactNode;
  align?: "left" | "center" | "right";
}

export interface TableProps<T> extends Omit<TableHTMLAttributes<HTMLTableElement>, "children"> {
  columns: TableColumn<T>[];
  data: T[];
  rowKey?: keyof T | ((row: T, index: number) => string);
  caption?: string;
}

export function Table<T>({ columns, data, rowKey, caption, className, ...props }: TableProps<T>) {
  return (
    <div className="dd-root dd-table-wrap">
      <table {...props} className={cx("dd-table", className)}>
        {caption ? <caption style={{ textAlign: "left", padding: "var(--space-3)", color: "var(--color-text-secondary)" }}>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={String(column.key)}
                scope="col"
                style={{ width: column.width, textAlign: column.align ?? "left" }}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => {
            const resolvedKey =
              typeof rowKey === "function"
                ? rowKey(row, rowIndex)
                : rowKey
                  ? String(row[rowKey as keyof T])
                  : String(rowIndex);

            return (
              <tr key={resolvedKey}>
                {columns.map((column) => {
                  const value = row[column.key as keyof T];
                  return (
                    <td key={String(column.key)} style={{ textAlign: column.align ?? "left" }}>
                      {column.render ? column.render(row, rowIndex) : (value as ReactNode)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
