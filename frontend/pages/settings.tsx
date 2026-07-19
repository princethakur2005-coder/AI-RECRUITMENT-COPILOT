import { authFetch } from "../lib/api";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Alert,
  AppLayout,
  Badge,
  Button,
  Checkbox,
  ContentContainer,
  EmptyState,
  ErrorState,
  FormActions,
  FormWrapper,
  Header,
  Input,
  LoadingState,
  Section,
  Select,
  Stack,
  Switch,
} from "../components";


interface WorkspaceRecord {
  id: string;
  name?: string;
  settings?: Record<string, unknown>;
}

interface PreferencesPayload {
  preferences?: {
    theme?: string;
    notifications_enabled?: boolean;
    timezone?: string;
    language?: string;
    compact_mode?: boolean;
    ai_assist_level?: string;
    ai_placeholder_enabled?: boolean;
    security_placeholder_enabled?: boolean;
    [key: string]: unknown;
  };
}

const ORG_ID = "default";
const WORKSPACES_ENDPOINT = `/orgs/${ORG_ID}/workspaces`;

export default function SettingsPage() {
  const [workspace, setWorkspace] = useState<WorkspaceRecord | null>(null);

  const [theme, setTheme] = useState("system");
  const [timezone, setTimezone] = useState("UTC");
  const [language, setLanguage] = useState("en-US");

  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [compactMode, setCompactMode] = useState(false);

  const [aiAssistLevel, setAiAssistLevel] = useState("balanced");
  const [aiPlaceholderEnabled, setAiPlaceholderEnabled] = useState(true);
  const [securityPlaceholderEnabled, setSecurityPlaceholderEnabled] = useState(true);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const listResponse = await authFetch(WORKSPACES_ENDPOINT, {
        headers: {
          Accept: "application/json",
        },
      });

      if (!listResponse.ok) {
        throw new Error(`Failed to load workspace settings (${listResponse.status})`);
      }

      const listPayload = (await listResponse.json()) as WorkspaceRecord[];
      const selected = Array.isArray(listPayload) && listPayload.length ? listPayload[0] : null;
      setWorkspace(selected);

      const settings = (selected?.settings ?? {}) as Record<string, unknown>;
      const prefs = (settings.preferences ?? settings) as Record<string, unknown>;

      setTheme(String(prefs.theme ?? "system"));
      setTimezone(String(prefs.timezone ?? "UTC"));
      setLanguage(String(prefs.language ?? "en-US"));

      setNotificationsEnabled(Boolean(prefs.notifications_enabled ?? true));
      setCompactMode(Boolean(prefs.compact_mode ?? false));

      setAiAssistLevel(String(prefs.ai_assist_level ?? "balanced"));
      setAiPlaceholderEnabled(Boolean(prefs.ai_placeholder_enabled ?? true));
      setSecurityPlaceholderEnabled(Boolean(prefs.security_placeholder_enabled ?? true));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load settings");
      setWorkspace(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const settingsPayload = useMemo(
    () => ({
      preferences: {
        theme,
        timezone,
        language,
        notifications_enabled: notificationsEnabled,
        compact_mode: compactMode,
        ai_assist_level: aiAssistLevel,
        ai_placeholder_enabled: aiPlaceholderEnabled,
        security_placeholder_enabled: securityPlaceholderEnabled,
      },
    }),
    [aiAssistLevel, aiPlaceholderEnabled, compactMode, language, notificationsEnabled, securityPlaceholderEnabled, theme, timezone],
  );

  const saveSettings = async () => {
    if (!workspace?.id) {
      setError("No workspace available to save settings");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await authFetch(`${WORKSPACES_ENDPOINT}/${workspace.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ settings: settingsPayload }),
      });

      if (!response.ok) {
        throw new Error(`Failed to save settings (${response.status})`);
      }

      setSuccess("Settings saved successfully.");
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout
      className="settings-page"
      header={
        <Header
          left={
            <Stack gap="1">
              <h1 className="settings-title">Settings</h1>
              <p className="settings-subtitle">Configure application, account, AI, and security workspace preferences.</p>
            </Stack>
          }
          right={
            <div className="settings-actions">
              <Button variant="secondary" size="sm" onClick={() => void loadSettings()}>
                Refresh
              </Button>
              <Button size="sm" onClick={() => void saveSettings()} disabled={saving || loading || !workspace}>
                {saving ? "Saving..." : "Save Settings"}
              </Button>
            </div>
          }
        />
      }
    >
      <ContentContainer className="settings-main" fluid>
        {loading ? <LoadingState title="Loading settings" description="Fetching workspace and preference settings." /> : null}
        {!loading && error ? <ErrorState title="Unable to load settings" description={error} onRetry={() => void loadSettings()} /> : null}
        {!loading && !error && !workspace ? (
          <EmptyState
            title="No settings workspace found"
            description="Settings become available when a workspace is configured."
            actionLabel="Reload"
            onAction={() => void loadSettings()}
          />
        ) : null}

        {!loading && !error && workspace ? (
          <Stack gap="4">
            {success ? <Alert tone="success" title="Updated" description={success} /> : null}

            <div className="settings-grid">
              <Section elevated>
                <Stack gap="3">
                  <strong>Application Settings</strong>
                  <FormWrapper
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveSettings();
                    }}
                    columns={2}
                  >
                    <Select
                      label="Theme Preference"
                      value={theme}
                      onChange={(event) => setTheme(event.target.value)}
                      options={[
                        { value: "system", label: "System" },
                        { value: "light", label: "Light" },
                        { value: "dark", label: "Dark" },
                      ]}
                    />
                    <Select
                      label="Timezone"
                      value={timezone}
                      onChange={(event) => setTimezone(event.target.value)}
                      options={[
                        { value: "UTC", label: "UTC" },
                        { value: "Asia/Kolkata", label: "Asia/Kolkata" },
                        { value: "America/New_York", label: "America/New_York" },
                        { value: "Europe/London", label: "Europe/London" },
                      ]}
                    />
                    <Input label="Language" value={language} onChange={(event) => setLanguage(event.target.value)} />
                    <Switch
                      label="Compact Mode"
                      description="Use a denser layout for workspace pages."
                      checked={compactMode}
                      onCheckedChange={setCompactMode}
                    />
                    <FormActions submitLabel="Save Application Settings" submitting={saving} />
                  </FormWrapper>
                </Stack>
              </Section>

              <Section elevated>
                <Stack gap="3">
                  <strong>Account Preferences</strong>
                  <Switch
                    label="Enable Notifications"
                    description="Receive in-app workspace notifications."
                    checked={notificationsEnabled}
                    onCheckedChange={setNotificationsEnabled}
                  />
                  <Checkbox
                    label="Show profile activity summary"
                    description="Display recent activity cards in profile overview."
                    checked
                    onChange={() => {
                      return;
                    }}
                  />
                  <Badge tone="brand">Workspace: {workspace.name || workspace.id}</Badge>
                </Stack>
              </Section>

              <Section elevated>
                <Stack gap="3">
                  <strong>AI Preferences (Placeholders)</strong>
                  <Select
                    label="AI Assist Level"
                    value={aiAssistLevel}
                    onChange={(event) => setAiAssistLevel(event.target.value)}
                    options={[
                      { value: "low", label: "Low" },
                      { value: "balanced", label: "Balanced" },
                      { value: "aggressive", label: "Aggressive" },
                    ]}
                  />
                  <Switch
                    label="Enable AI Placeholder Features"
                    description="Reserved UI toggle for future AI preference controls."
                    checked={aiPlaceholderEnabled}
                    onCheckedChange={setAiPlaceholderEnabled}
                  />
                  <p className="settings-placeholder">AI preference controls are placeholders only.</p>
                </Stack>
              </Section>

              <Section elevated>
                <Stack gap="3">
                  <strong>Security Settings (Placeholders)</strong>
                  <Switch
                    label="Enable Security Placeholder"
                    description="Reserved UI toggle for future security controls."
                    checked={securityPlaceholderEnabled}
                    onCheckedChange={setSecurityPlaceholderEnabled}
                  />
                  <Alert tone="info" description="Security settings are placeholder-only in this implementation." />
                </Stack>
              </Section>
            </div>
          </Stack>
        ) : null}
      </ContentContainer>
    </AppLayout>
  );
}


