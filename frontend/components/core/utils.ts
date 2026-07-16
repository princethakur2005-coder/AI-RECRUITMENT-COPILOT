export function cx(...parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

export function getInitials(name?: string): string {
  if (!name) {
    return "?";
  }

  const pieces = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);

  if (!pieces.length) {
    return "?";
  }

  return pieces.map((part) => part[0]?.toUpperCase() ?? "").join("");
}
