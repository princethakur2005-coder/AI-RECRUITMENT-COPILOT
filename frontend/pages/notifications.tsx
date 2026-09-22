import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AppLayout,
  Badge,
  Button,
  ContentContainer,
  EmptyState,
  ErrorState,
  Header,
  Input,
  LoadingState,
  MetricCard,
  Pagination,
  Section,
  Select,
  Stack,
  Table,
} from "../components";


type NotificationPriority = "low" | "medium" | "high" | "urgent" | string;
type NotificationCategory = "system" | "candidate" | "interview" | "offer" | "task" | string;

interface NotificationRecord {
  id: string;
  title?: string;
  message?: string;
  type?: NotificationCategory;
  priority?: NotificationPriority;
  read?: boolean;
  created_at?: string;
  [key: string]: unknown;
}

interface NotificationResponse {
  items?: NotificationRecord[];
  notifications?: NotificationRecord[];
  total?: number;
  unread?: number;
}

const NOTIFICATIONS_ENDPOINT = "/api/notifications";

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function toneForPriority(priority?: string): "neutral" | "brand" | "success" | "warning" | "danger" {
  const value = String(priority ?? "").toLowerCase();
  if (value.includes("urgent") || value.includes("critical")) return "danger";
  if (value.includes("high")) return "warning";
  if (value.includes("medium")) return "brand";
  if (value.includes("low")) return "success";
  return "neutral";
}

function toneForRead(read: boolean): "neutral" | "success" {
  return read ? "success" : "neutral";
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [readFilter, setReadFilter] = useState<"all" | "read" | "unread">("all");
  const [categoryFilter, setCategoryFilter] = useState<"all" | string>("all");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      let response = await authFetch(NOTIFICATIONS_ENDPOINT, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok && response.status === 404) {
        response = await authFetch("/api/v1/notifications", {
          headers: {
            Accept: "application/json",
          },
        });
      }

      if (!response.ok) {
        throw new Error(`Failed to load notifications (${response.status})`);
      }

      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        setNotifications([]);
        return;
      }

      const payload = (await response.json()) as NotificationResponse | NotificationRecord[];
      if (Array.isArray(payload)) {
        setNotifications(payload);
      } else {
        const resolved = payload.items ?? payload.notifications ?? [];
        setNotifications(Array.isArray(resolved) ? resolved : []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load notifications");
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  const categories = useMemo(() => {
    const values = Array.from(new Set(notifications.map((item) => String(item.type ?? "system").toLowerCase())));
    return values.sort();
  }, [notifications]);

  const filtered = useMemo(() => {
    const normalized = search.trim().toLowerCase();

    return notifications.filter((item) => {
      const matchesSearch =
        !normalized ||
        String(item.title ?? "").toLowerCase().includes(normalized) ||
        String(item.message ?? "").toLowerCase().includes(normalized);

      const read = Boolean(item.read);
      const matchesRead = readFilter === "all" || (readFilter === "read" ? read : !read);
      const category = String(item.type ?? "system").toLowerCase();
      const matchesCategory = categoryFilter === "all" || category === categoryFilter;

      return matchesSearch && matchesRead && matchesCategory;
    });
  }, [categoryFilter, notifications, readFilter, search]);

  const totals = useMemo(() => {
    const total = notifications.length;
    const unread = notifications.filter((item) => !item.read).length;
    const read = total - unread;
    const highPriority = notifications.filter((item) => {
      const value = String(item.priority ?? "").toLowerCase();
      return value.includes("high") || value.includes("urgent") || value.includes("critical");
    }).length;
    return { total, unread, read, highPriority };
  }, [notifications]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const paged = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  const patchNotification = async (id: string, payload: Record<string, unknown>) => {
    await authFetch(`${NOTIFICATIONS_ENDPOINT}/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
  };

  const markAsRead = async (id: string) => {
    await patchNotification(id, { read: true });
    await loadNotifications();
  };

  const markAsUnread = async (id: string) => {
    await patchNotification(id, { read: false });
    await loadNotifications();
  };

  const markAllAsRead = async () => {
    if (!totals.unread) return;
    await authFetch(`${NOTIFICATIONS_ENDPOINT}/read-all`, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    await loadNotifications();
  };

  return (
    <AppLayout
      className="notifications-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="notifications-title">Notification Center</h1>
              <p className="notifications-subtitle">Manage notification list, categories, and read/unread workflows.</p>
            </Stack>
          }
          right={
            <div className="notifications-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadNotifications()}>
                Refresh
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void markAllAsRead()} disabled={!totals.unread}>
                Mark All Read
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="notifications-main" fluid>
        {loading ? <LoadingState title="Loading notifications" description="Fetching notification center data." /> : null}
        {!loading && error ? <ErrorState title="Unable to load notifications" description={error} onRetry={() => void loadNotifications()} /> : null}
        {!loading && !error && !notifications.length ? (
          <EmptyState
            title="No notifications"
            description="Notifications will appear here when system and recruitment events are generated."
            actionLabel="Reload"
            onAction={() => void loadNotifications()}
          />
        ) : null}

        {!loading && !error && notifications.length ? (
          <Stack gap="5">
            <section aria-label="Notification summary cards">
              <div className="notifications-summary-grid">
                <MetricCard label="Total" value={totals.total} />
                <MetricCard label="Unread" value={totals.unread} />
                <MetricCard label="Read" value={totals.read} />
                <MetricCard label="High Priority" value={totals.highPriority} />
              </div>
            </section>

            <Section>
              <div className="notifications-toolbar">
                <Input
                  label="Search"
                  placeholder="Search notifications"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setPage(1);
                  }}
                />
                <Select
                  label="Read Status"
                  value={readFilter}
                  onChange={(event) => {
                    setReadFilter(event.target.value as typeof readFilter);
                    setPage(1);
                  }}
                  options={[
                    { value: "all", label: "All" },
                    { value: "unread", label: "Unread" },
                    { value: "read", label: "Read" },
                  ]}
                />
                <Select
                  label="Category"
                  value={categoryFilter}
                  onChange={(event) => {
                    setCategoryFilter(event.target.value);
                    setPage(1);
                  }}
                  options={[
                    { value: "all", label: "All Categories" },
                    ...categories.map((item) => ({ value: item, label: item })),
                  ]}
                />
                <Select
                  label="Page Size"
                  value={String(pageSize)}
                  onChange={(event) => {
                    setPageSize(Number(event.target.value));
                    setPage(1);
                  }}
                  options={[
                    { value: "10", label: "10" },
                    { value: "20", label: "20" },
                    { value: "50", label: "50" },
                  ]}
                />
              </div>
            </Section>

            {!filtered.length ? (
              <EmptyState title="No matching notifications" description="Adjust notification filters or search terms." />
            ) : (
              <Section>
                <Table
                  caption="Notification list"
                  columns={[
                    {
                      key: "title",
                      header: "Notification",
                      render: (row: NotificationRecord) => (
                        <Stack gap="1">
                          <strong>{row.title || "Notification"}</strong>
                          <span>{row.message || "No message"}</span>
                        </Stack>
                      ),
                    },
                    {
                      key: "type",
                      header: "Category",
                      render: (row: NotificationRecord) => <span className="notification-type">{row.type || "system"}</span>,
                    },
                    {
                      key: "priority",
                      header: "Priority",
                      render: (row: NotificationRecord) => (
                        <Badge tone={toneForPriority(row.priority)}>{row.priority || "normal"}</Badge>
                      ),
                    },
                    {
                      key: "read",
                      header: "Status",
                      render: (row: NotificationRecord) => (
                        <Badge tone={toneForRead(Boolean(row.read))}>{row.read ? "Read" : "Unread"}</Badge>
                      ),
                    },
                    {
                      key: "created_at",
                      header: "Created",
                      render: (row: NotificationRecord) => formatDate(row.created_at),
                    },
                    {
                      key: "actions",
                      header: "Actions",
                      render: (row: NotificationRecord) => (
                        <div className="notifications-actions">
                          {row.read ? (
                            <Button size="sm" variant="secondary" onClick={() => void markAsUnread(row.id)}>
                              Mark Unread
                            </Button>
                          ) : (
                            <Button size="sm" onClick={() => void markAsRead(row.id)}>
                              Mark Read
                            </Button>
                          )}
                        </div>
                      ),
                    },
                  ]}
                  data={paged}
                  rowKey="id"
                />

                <Pagination page={page} pageSize={pageSize} total={total} onPageChange={setPage} showPageButtons siblingCount={1} />
              </Section>
            )}
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}


