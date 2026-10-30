import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { defaultApi } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { getDefaultAuthenticatedPath } from '@/lib/userAccess';

export function LoginPage() {
  const { user, loading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!loading && user) navigate(getDefaultAuthenticatedPath(user), { replace: true });
  }, [loading, user, navigate]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await defaultApi.login(email.trim(), password);
      setPassword('');
      if (result.passwordChangeRequired === true) {
        navigate('/set-password', { replace: true });
        return;
      }
      if (result.authenticated !== true) throw new Error('Sign-in could not be confirmed.');
      const signedIn = await refreshUser();
      if (!signedIn) throw new Error('Sign-in could not be confirmed.');
      navigate(getDefaultAuthenticatedPath(signedIn), { replace: true });
    } catch (failure) {
      setPassword('');
      setError(failure instanceof Error ? failure.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader
        label="Login"
        title="Staff sign-in"
        description="Use your individual staff account. An administrator creates accounts and assigns access."
      />
      <form
        onSubmit={(event) => {
          void submit(event);
        }}
        className="surface-card mx-auto mt-8 w-full max-w-xl space-y-4 p-6"
      >
        <fieldset disabled={busy} className="space-y-4">
          <label className="block">
            Email address
            <input
              id="login-email"
              type="email"
              required
              maxLength={320}
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="field-input mt-1 w-full rounded-md px-3 py-2"
            />
          </label>
          <label className="block">
            Password
            <input
              id="login-password"
              type="password"
              required
              maxLength={256}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="field-input mt-1 w-full rounded-md px-3 py-2"
            />
          </label>
          {error && (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          )}
          <Button type="submit">{busy ? 'Signing in…' : 'Sign in'}</Button>
        </fieldset>
        <p className="text-sm text-muted-foreground">
          Need an account or a password reset? Contact a project administrator. There is no public
          registration.
        </p>
      </form>
    </>
  );
}
