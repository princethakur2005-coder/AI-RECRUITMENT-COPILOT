import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AppLayout,
  Button,
  ContentContainer,
  EmptyState,
  ErrorState,
  FormActions,
  FormWrapper,
  Header,
  Input,
  LoadingState,
  MetricCard,
  Section,
  Stack,
  Table,
  Textarea,
} from "../components";
import "./user-profile.css";

interface UserRecord {
  id: string;
  email?: string;
  full_name?: string;
  role?: string;
  created_at?: string;
  updated_at?: string;
  summary?: string;
  avatar_url?: string;
  [key: string]: unknown;
}

const USERS_ENDPOINT = "/users";

function formatDate(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "U";
  return parts.slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("");
}

export default function UserProfilePage() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [user, setUser] = useState<UserRecord | null>(null);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [summary, setSummary] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(USERS_ENDPOINT, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to load users (${response.status})`);
      }

      const payload = (await response.json()) as UserRecord[];
      const list = Array.isArray(payload) ? payload : [];
      setUsers(list);

      const selected = list.length ? list[0] : null;
      setUser(selected);

      setFullName(String(selected?.full_name ?? ""));
      setEmail(String(selected?.email ?? ""));
      setRole(String(selected?.role ?? ""));
      setSummary(String(selected?.summary ?? ""));
      setAvatarUrl(String(selected?.avatar_url ?? ""));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load profile");
      setUsers([]);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const saveProfile = async () => {
    if (!user?.id) {
      setError("No user profile available to update");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(`${USERS_ENDPOINT}/${user.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          full_name: fullName,
          email,
          role,
          summary,
          avatar_url: avatarUrl,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to save profile (${response.status})`);
      }

      setSuccess("Profile updated successfully.");
      await loadProfile();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update profile");
    } finally {
      setSaving(false);
    }
  };

  const activityRows = useMemo(
    () =>
      users.slice(0, 10).map((item) => ({
        id: item.id,
        activity: `Profile sync: ${item.full_name || item.email || item.id}`,
        role: item.role || "user",
        timestamp: formatDate(item.updated_at || item.created_at),
      })),
    [users],
  );

  const activitySummary = useMemo(() => {
    const total = users.length;
    const admins = users.filter((item) => String(item.role ?? "").toLowerCase().includes("admin")).length;
    const active = users.filter((item) => Boolean(item.updated_at || item.created_at)).length;
    return { total, admins, active };
  }, [users]);

  const displayName = fullName || email || "User";

  return (
    <AppLayout
      className="user-profile-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="user-profile-title">User Profile</h1>
              <p className="user-profile-subtitle">Profile overview, account information, avatar UI, and activity summary.</p>
            </Stack>
          }
          right={
            <div className="user-profile-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadProfile()}>
                Refresh
              </Button>
              <Button size="sm" onClick={() => void saveProfile()} disabled={saving || loading || !user}>
                {saving ? "Saving..." : "Save Profile"}
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="user-profile-main" fluid>
        {loading ? <LoadingState title="Loading user profile" description="Fetching user and profile information." /> : null}
        {!loading && error ? <ErrorState title="Unable to load profile" description={error} onRetry={() => void loadProfile()} /> : null}
        {!loading && !error && !user ? (
          <EmptyState
            title="No user profile found"
            description="User profile data will appear here when users are available."
            actionLabel="Reload"
            onAction={() => void loadProfile()}
          />
        ) : null}

        {!loading && !error && user ? (
          <Stack gap="4">
            {success ? <Alert tone="success" title="Profile Updated" description={success} /> : null}

            <section aria-label="Profile overview cards">
              <div className="user-profile-summary-grid">
                <MetricCard label="Users in Workspace" value={activitySummary.total} />
                <MetricCard label="Admin Users" value={activitySummary.admins} />
                <MetricCard label="Profiles Tracked" value={activitySummary.active} />
              </div>
            </section>

            <div className="user-profile-grid">
              <Section elevated>
                <Stack gap="3">
                  <strong>Profile Overview & Edit Profile</strong>
                  <div className="user-profile-avatar">
                    <div className="user-profile-avatar-preview" aria-label="Avatar preview">
                      {initials(displayName)}
                    </div>
                    <Input
                      label="Avatar URL (UI-only)"
                      value={avatarUrl}
                      onChange={(event) => setAvatarUrl(event.target.value)}
                      placeholder="https://example.com/avatar.png"
                    />
                    <small>Avatar management UI only. Upload backend is not implemented.</small>
                  </div>

                  <FormWrapper
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveProfile();
                    }}
                    columns={2}
                  >
                    <Input label="Full Name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
                    <Input label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
                    <Input label="Role" value={role} onChange={(event) => setRole(event.target.value)} />
                    <Input label="Account ID" value={user.id} disabled />
                    <Textarea
                      label="Profile Summary"
                      value={summary}
                      onChange={(event) => setSummary(event.target.value)}
                      placeholder="Add profile summary"
                    />
                    <FormActions submitLabel="Save Profile Changes" submitting={saving} />
                  </FormWrapper>
                </Stack>
              </Section>

              <Section elevated>
                <Stack gap="3">
                  <strong>Account Information</strong>
                  <Table
                    columns={[
                      { key: "field", header: "Field" },
                      { key: "value", header: "Value" },
                    ]}
                    data={[
                      { field: "User ID", value: user.id },
                      { field: "Email", value: user.email || "-" },
                      { field: "Role", value: user.role || "-" },
                      { field: "Created", value: formatDate(user.created_at) },
                      { field: "Updated", value: formatDate(user.updated_at) },
                    ]}
                    rowKey="field"
                  />

                  <strong>Activity Summary</strong>
                  {activityRows.length ? (
                    <Table
                      columns={[
                        { key: "activity", header: "Activity" },
                        { key: "role", header: "Role" },
                        { key: "timestamp", header: "Timestamp" },
                      ]}
                      data={activityRows}
                      rowKey="id"
                    />
                  ) : (
                    <EmptyState title="No activity yet" description="Profile activity summary will appear here." />
                  )}
                </Stack>
              </Section>
            </div>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}
