import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from '@/components/custom/PageHeader';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { API_BASE_PATH } from '@/api/defaultApi';
import { dispatchSessionExpiredEvent } from '@/lib/authSession';

type Staff = { id: string; email: string; isAdmin: boolean; roles: string[] };
type Assignment = {
  case_id: string;
  user_id: string;
  active: boolean;
  purpose: 'clinical-reference' | 'synthetic-research';
  scopes: string[];
  revision: number;
};
type Selection = {
  caseId: string;
  staff: Staff;
  assignment: Assignment | null;
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
  });
  const data: unknown = await response.json().catch(() => null);
  if (response.status === 401) dispatchSessionExpiredEvent();
  return { response, data };
}

export function AdminCaseAccessPage() {
  const [caseId, setCaseId] = useState('');
  const [email, setEmail] = useState('');
  const [selection, setSelection] = useState<Selection | null>(null);
  const [active, setActive] = useState(true);
  const [purpose, setPurpose] =
    useState<Assignment['purpose']>('clinical-reference');
  const [read, setRead] = useState(true);
  const [exportAllowed, setExportAllowed] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const epoch = useRef(0);
  useEffect(
    () => () => {
      epoch.current++;
    },
    [],
  );
  const invalidate = () => {
    epoch.current++;
    setSelection(null);
    setBusy(false);
    setMessage('');
  };

  const load = async (event: FormEvent) => {
    event.preventDefault();
    const id = caseId.trim().toLowerCase();
    if (!UUID.test(id)) {
      setMessage('Enter a valid case UUID.');
      return;
    }
    const ticket = ++epoch.current;
    setBusy(true);
    setSelection(null);
    setMessage('');
    try {
      const lookup = await request(
        `/admin/staff-lookup?email=${encodeURIComponent(email.trim())}`,
      );
      if (!lookup.response.ok)
        throw new Error(
          'Staff lookup failed. Your current admin access is required.',
        );
      const staff = (lookup.data as { user?: Staff } | null)?.user;
      if (!staff) throw new Error('No approved staff account was found.');
      const result = await request(`/admin/case-access/${id}/${staff.id}`);
      if (!result.response.ok && result.response.status !== 404)
        throw new Error('Case permission lookup failed.');
      const assignment =
        result.response.status === 404 ? null : (result.data as Assignment);
      if (
        assignment &&
        (assignment.case_id !== id ||
          assignment.user_id !== staff.id ||
          !Number.isSafeInteger(assignment.revision))
      )
        throw new Error('Invalid permission response.');
      if (ticket !== epoch.current) return;
      setSelection({ caseId: id, staff, assignment });
      setActive(assignment?.active ?? true);
      setPurpose(
        assignment?.purpose ??
          (staff.isAdmin || staff.roles.includes('practitioner')
            ? 'clinical-reference'
            : 'synthetic-research'),
      );
      setRead(assignment ? assignment.scopes.includes('read') : true);
      setExportAllowed(assignment?.scopes.includes('export') ?? false);
      setReason('');
      setMessage(
        assignment
          ? `Stored assignment, revision ${assignment.revision}.`
          : 'No stored assignment. Save checks that the case exists.',
      );
    } catch (error) {
      if (ticket === epoch.current)
        setMessage(
          error instanceof Error ? error.message : 'Permission lookup failed.',
        );
    } finally {
      if (ticket === epoch.current) setBusy(false);
    }
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!selection) return;
    const ticket = ++epoch.current;
    setBusy(true);
    setMessage('');
    try {
      const result = await request(
        `/admin/case-access/${selection.caseId}/${selection.staff.id}`,
        {
          method: 'PUT',
          body: JSON.stringify({
            expected_revision: selection.assignment?.revision ?? 0,
            active,
            purpose,
            scopes: [
              ...(read ? ['read'] : []),
              ...(exportAllowed ? ['export'] : []),
            ],
            reason: reason.trim(),
          }),
        },
      );
      if (result.response.status === 409)
        throw new Error(
          'This assignment changed. Load it again before you save.',
        );
      if (!result.response.ok)
        throw new Error(
          'Permission change was rejected. Check the case, role and current admin access.',
        );
      const saved = result.data as Assignment;
      if (
        saved.case_id !== selection.caseId ||
        saved.user_id !== selection.staff.id ||
        !Number.isSafeInteger(saved.revision)
      )
        throw new Error(
          'The saved assignment could not be confirmed. Load it again.',
        );
      if (ticket !== epoch.current) return;
      setSelection({ ...selection, assignment: saved });
      setReason('');
      setMessage(
        `Saved revision ${saved.revision}. New requests use these permissions.`,
      );
    } catch (error) {
      if (ticket === epoch.current)
        setMessage(
          error instanceof Error ? error.message : 'Permission change failed.',
        );
    } finally {
      if (ticket === epoch.current) setBusy(false);
    }
  };
  const inputClass =
    'w-full rounded-md border border-border bg-background px-3 py-2';
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <PageHeader
        label="Administration"
        title="Case permissions"
        description="Approval and a role do not grant case access. Each case needs an explicit assignment, including for admins."
      />
      <Link to="/admin/approvals" className="text-primary underline">
        Back to staff accounts
      </Link>
      <form
        onSubmit={(event) => {
          void load(event);
        }}
        className="space-y-4 rounded-xl border border-border bg-card p-5"
      >
        <fieldset disabled={busy} className="space-y-4">
          <label className="block">
            Case UUID
            <input
              required
              value={caseId}
              onChange={(e) => {
                invalidate();
                setCaseId(e.target.value);
              }}
              className={inputClass}
            />
          </label>
          <label className="block">
            Approved staff email
            <input
              type="email"
              required
              maxLength={320}
              value={email}
              onChange={(e) => {
                invalidate();
                setEmail(e.target.value);
              }}
              className={inputClass}
            />
          </label>
          <Button disabled={busy} type="submit">
            Load assignment
          </Button>
        </fieldset>
      </form>
      {message && (
        <p role="status" className="rounded-lg border border-border p-4">
          {message}
        </p>
      )}
      {selection && (
        <form
          onSubmit={(event) => {
            void save(event);
          }}
          className="space-y-4 rounded-xl border border-border bg-card p-5"
        >
          <fieldset disabled={busy} className="space-y-4">
            <p>Staff: {selection.staff.email}</p>
            <p className="break-all text-sm">Case: {selection.caseId}</p>
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
              Assignment active
            </label>
            <div className="space-y-1">
              <label htmlFor="case-purpose">Purpose</label>
              <Select
                value={purpose}
                onValueChange={(value) =>
                  setPurpose(value as Assignment['purpose'])
                }
                disabled={busy}
              >
                <SelectTrigger id="case-purpose">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="clinical-reference">
                    Clinical reference (practitioner or admin)
                  </SelectItem>
                  <SelectItem value="synthetic-research">
                    Synthetic research (researcher or admin)
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={read}
                onChange={(e) => {
                  setRead(e.target.checked);
                  if (!e.target.checked) setExportAllowed(false);
                }}
              />
              Read case data
            </label>
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={exportAllowed}
                disabled={!read}
                onChange={(e) => setExportAllowed(e.target.checked)}
              />
              Allow export
            </label>
            <p className="text-sm text-muted-foreground">
              Export permission is recorded here. The old broad export route
              remains blocked until a case-scoped export feature is available.
            </p>
            <label className="block">
              Reason for this change
              <textarea
                required
                minLength={1}
                maxLength={256}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className={inputClass}
              />
            </label>
            <Button
              type="submit"
              disabled={busy || !reason.trim() || (active && !read)}
            >
              Save permissions
            </Button>
          </fieldset>
        </form>
      )}
    </div>
  );
}
