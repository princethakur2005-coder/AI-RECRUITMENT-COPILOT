export function cx(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export type SpaceToken =
  | "0"
  | "1"
  | "2"
  | "3"
  | "4"
  | "5"
  | "6"
  | "8"
  | "10"
  | "12"
  | "16"
  | "20";

export function spaceVar(token?: SpaceToken): string | undefined {
  if (!token) {
    return undefined;
  }
  return `var(--space-${token})`;
}
