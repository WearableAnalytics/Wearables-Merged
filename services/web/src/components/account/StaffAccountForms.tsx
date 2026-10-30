import { useState, type FormEvent } from 'react';
import { defaultApi, type NonAdminRole } from '@/api/defaultApi';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AccessProfileHelp } from './AccessProfileHelp';
import type { AdminUser } from '@/pages/admin-approvals/components/types';

function TemporaryPassword({
  value,
  onChange,
  id,
}: {
  value: string;
  onChange: (value: string) => void;
  id: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-2">
      <label className="block">
        Temporary setup password
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          required
          minLength={15}
          maxLength={256}
          autoComplete="new-password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="field-input mt-1 w-full rounded-md px-3 py-2"
        />
      </label>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            onChange(
              Array.from(crypto.getRandomValues(new Uint8Array(24)), (byte) =>
                byte.toString(16).padStart(2, '0'),
              ).join(''),
            )
          }
        >
          Generate
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => setVisible(!visible)}
        >
          {visible ? 'Hide' : 'Show'}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Give this password to the user through your approved channel. It expires
        after 24 hours and allows only password setup. No invitation email is
        sent.
      </p>
    </div>
  );
}

export function CreateStaffAccountForm({
  onSaved,
}: {
  onSaved: () => Promise<void>;
}) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [profile, setProfile] = useState('practitioner');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    setFailed(false);
    const roles: NonAdminRole[] =
      profile === 'admin'
        ? []
        : profile === 'both'
          ? ['practitioner', 'researcher']
          : [profile as NonAdminRole];
    try {
      await defaultApi.createStaff({
        email: email.trim(),
        name: name.trim() || undefined,
        isAdmin: profile === 'admin',
        roles,
        temporaryPassword: password,
      });
      setPassword('');
      setName('');
      setEmail('');
      await onSaved();
      setMessage(
        'Staff account created. The user must choose their own password on first sign-in. Assign case access separately.',
      );
    } catch (error) {
      setFailed(true);
      setMessage(
        error instanceof Error ? error.message : 'Account creation failed.',
      );
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
      <h2 className="text-section-title">Create staff account</h2>
      <p className="text-sm text-muted-foreground">
        Each person gets an individual account. An admin role manages accounts;
        it does not grant automatic access to case data.
      </p>
      <fieldset disabled={busy} className="space-y-4">
        <label className="block">
          Staff email
          <input
            id="staff-email"
            type="email"
            required
            maxLength={320}
            value={email}
            autoComplete="off"
            onChange={(e) => setEmail(e.target.value)}
            className="field-input mt-1 w-full rounded-md px-3 py-2"
          />
        </label>
        <label className="block">
          Name (optional)
          <input
            id="staff-name"
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="field-input mt-1 w-full rounded-md px-3 py-2"
          />
        </label>
        <div className="space-y-1">
          <div className="flex items-center gap-1">
            <label htmlFor="staff-profile">Access profile</label>
            <AccessProfileHelp />
          </div>
          <Select value={profile} onValueChange={setProfile} disabled={busy}>
            <SelectTrigger id="staff-profile">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="practitioner">Practitioner</SelectItem>
              <SelectItem value="researcher">Researcher</SelectItem>
              <SelectItem value="both">Practitioner + Researcher</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <TemporaryPassword
          value={password}
          onChange={setPassword}
          id="staff-temporary-password"
        />
        <Button type="submit">
          {busy ? 'Creating…' : 'Create staff account'}
        </Button>
      </fieldset>
      {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    </form>
  );
}

export function ResetStaffPasswordForm({
  target,
  onDone,
  onCancel,
}: {
  target: AdminUser;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (!Number.isSafeInteger(target.revision))
        throw new Error('Reload this account before resetting its password.');
      await defaultApi.resetStaffPassword(
        target.id,
        target.revision!,
        password,
      );
      setPassword('');
      onDone();
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : 'Password reset failed.',
      );
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
      <h2 className="text-section-title">Reset password: {target.email}</h2>
      <p className="text-sm text-muted-foreground">
        This invalidates the user's old sessions. The user must change the new
        setup password before normal access.
      </p>
      <fieldset disabled={busy} className="space-y-4">
        <TemporaryPassword
          value={password}
          onChange={setPassword}
          id="reset-temporary-password"
        />
        <div className="flex gap-2">
          <Button type="submit">
            {busy ? 'Resetting…' : 'Reset password'}
          </Button>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </fieldset>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
