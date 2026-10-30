import { PageHeader } from '@/components/custom/PageHeader';
import { Button } from '@/components/ui/button';
import { PasswordChangeForm } from '@/components/account/PasswordChangeForm';
import { useAuth } from '@/context/AuthContext';
import { useTheme, type ThemePreference } from '@/context/ThemeContext';
import { formatAccessLabel } from '@/lib/userAccess';

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System theme' },
  { value: 'light', label: 'Light mode' },
  { value: 'dark', label: 'Dark mode' },
];
export function AccountPage() {
  const { user } = useAuth();
  const { preference, setThemePreference } = useTheme();
  if (!user) return null;
  return (
    <>
      <PageHeader
        label="Account"
        title="Your account"
        description="Review your access and manage your own password. Ask an administrator for changes to roles or case access."
      />
      <section className="surface-card mt-6 space-y-2 p-5">
        <p className="text-sm text-muted-foreground">Email</p>
        <p>{user.email}</p>
        <p className="text-sm text-muted-foreground">Access</p>
        <p>{formatAccessLabel(user)}</p>
      </section>
      <section className="surface-card mt-6 space-y-3 p-5">
        <h2 className="text-section-title">Theme</h2>
        {THEMES.map((theme) => (
          <Button
            key={theme.value}
            type="button"
            onClick={() => setThemePreference(theme.value)}
            variant={preference === theme.value ? 'default' : 'outline'}
            aria-pressed={preference === theme.value}
          >
            {theme.label}
          </Button>
        ))}
      </section>
      <PasswordChangeForm />
    </>
  );
}
