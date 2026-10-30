import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { defaultApi } from '@/api/defaultApi';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { getDefaultAuthenticatedPath } from '@/lib/userAccess';

export function PasswordChangeForm({ initial = false }: { initial?: boolean }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);
  const { refreshUser } = useAuth();
  const navigate = useNavigate();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage('');
    setFailed(false);
    if (next !== repeat) {
      setMessage('The new passwords do not match.');
      setFailed(true);
      return;
    }
    setBusy(true);
    try {
      await defaultApi.changePassword(current, next, initial);
      setCurrent('');
      setNext('');
      setRepeat('');
      const user = await refreshUser();
      if (!user) throw new Error('Sign in again to confirm the changed password.');
      if (initial) navigate(getDefaultAuthenticatedPath(user), { replace: true });
      else setMessage('Password changed. Your earlier sessions have been invalidated.');
    } catch (error) {
      setCurrent('');
      setNext('');
      setRepeat('');
      setFailed(true);
      setMessage(error instanceof Error ? error.message : 'The password change was rejected.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      onSubmit={(event) => {
        void submit(event);
      }}
      className="surface-card mt-6 space-y-4 p-5"
    >
      <h2 className="text-section-title">
        {initial ? 'Choose your own password' : 'Change your password'}
      </h2>
      <p className="text-sm text-muted-foreground">
        Use a long, uncommon passphrase of at least 15 characters. Passwords are case-sensitive;
        spaces count.
      </p>
      <fieldset disabled={busy} className="space-y-4">
        <label className="block">
          {initial ? 'Temporary setup password' : 'Current password'}
          <input
            type="password"
            required
            maxLength={256}
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="field-input mt-1 w-full rounded-md px-3 py-2"
          />
        </label>
        <label className="block">
          New password
          <input
            type="password"
            required
            minLength={15}
            maxLength={256}
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className="field-input mt-1 w-full rounded-md px-3 py-2"
          />
        </label>
        <label className="block">
          Repeat new password
          <input
            type="password"
            required
            minLength={15}
            maxLength={256}
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            className="field-input mt-1 w-full rounded-md px-3 py-2"
          />
        </label>
        <Button type="submit">{busy ? 'Saving…' : 'Save password'}</Button>
      </fieldset>
      {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    </form>
  );
}
