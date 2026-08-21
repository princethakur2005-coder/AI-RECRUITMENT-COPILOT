import { readFileSync } from "fs";
import { join } from "path";

describe("notification API routing contract", () => {
  it("uses /api/notifications so the /notifications page is not shadowed", () => {
    const page = readFileSync(join(__dirname, "../../pages/notifications.tsx"), "utf8");
    const nextConfig = readFileSync(join(__dirname, "../../next.config.ts"), "utf8");

    expect(page).toContain('const NOTIFICATIONS_ENDPOINT = "/api/notifications"');
    expect(page).toContain("${NOTIFICATIONS_ENDPOINT}/read-all");
    expect(nextConfig).toContain('source: "/api/:path*"');
    expect(nextConfig).not.toContain('source: "/notifications/:path*"');
    expect(nextConfig).not.toContain('source: "/notifications"');
  });
});
