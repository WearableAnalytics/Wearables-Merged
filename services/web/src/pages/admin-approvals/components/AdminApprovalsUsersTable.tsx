import { Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AdminApprovalsEmptyState } from './AdminApprovalsEmptyState';
import type {
  AccessProfile,
  AdminUser,
  UserDraft,
  UserDraftEdits,
  UserStatus,
} from './types';

const ACCESS_PROFILE_OPTIONS: Array<{ value: AccessProfile; label: string }> = [
  { value: 'admin', label: 'Admin' },
  { value: 'practitioner', label: 'Practitioner' },
  { value: 'researcher', label: 'Researcher' },
  { value: 'practitioner_researcher', label: 'Practitioner + Researcher' },
];

const toAccessProfile = (entry: AdminUser): AccessProfile => {
  if (entry.isAdmin) return 'admin';
  const roles = new Set(entry.roles ?? []);
  const hasPractitioner = roles.has('practitioner');
  const hasResearcher = roles.has('researcher');

  if (hasPractitioner && hasResearcher) return 'practitioner_researcher';
  if (hasResearcher) return 'researcher';
  return 'practitioner';
};

type AdminApprovalsUsersTableProps = {
  users: AdminUser[];
  onResetPassword: (entry: AdminUser) => void;
  resetDisabled: boolean;
  currentUserId?: string;
  actionUserId: string | null;
  draftEdits: UserDraftEdits;
  onDraftUpdate: (entry: AdminUser, updates: Partial<UserDraft>) => void;
  onUpdate: (entry: AdminUser) => void;
};

export function AdminApprovalsUsersTable({
  users,
  onResetPassword,
  resetDisabled,
  currentUserId,
  actionUserId,
  draftEdits,
  onDraftUpdate,
  onUpdate,
}: AdminApprovalsUsersTableProps) {
  return (
    <div className="mt-4 overflow-auto">
      {users.length === 0 ? (
        <AdminApprovalsEmptyState
          title="No users match this search."
          description="Try a different name or email to see results."
          icon={<Inbox className="h-4 w-4" />}
        />
      ) : (
        <table className="table-grid">
          <thead className="table-head">
            <tr className="table-row">
              <th className="px-3 py-3">Email</th>
              <th className="px-3 py-3">Access profile</th>
              <th className="px-3 py-3">Access</th>
              <th className="px-3 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {users.map((entry) => {
              const isSelf = currentUserId === entry.id;
              const currentAccessProfile = toAccessProfile(entry);
              const currentStatus = (entry.status ?? 'approved') as UserStatus;
              const draft = draftEdits[entry.id] ?? {
                accessProfile: currentAccessProfile,
                status: currentStatus,
              };
              const isDirty =
                draft.accessProfile !== currentAccessProfile ||
                draft.status !== currentStatus;
              const isBusy = actionUserId === entry.id;

              return (
                <tr key={entry.id} className="table-row last:border-b-0">
                  <td className="px-3 py-3 font-medium text-foreground">
                    {entry.email}
                  </td>
                  <td className="px-3 py-3">
                    <Select
                      value={draft.accessProfile}
                      onValueChange={(value) =>
                        onDraftUpdate(entry, {
                          accessProfile: value as AccessProfile,
                        })
                      }
                      disabled={isSelf || isBusy}
                    >
                      <SelectTrigger
                        aria-label={`Access profile for ${entry.email}`}
                        className="min-w-[200px]"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ACCESS_PROFILE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-3 py-3">
                    <Select
                      value={draft.status}
                      onValueChange={(value) =>
                        onDraftUpdate(entry, { status: value as UserStatus })
                      }
                      disabled={isSelf || isBusy}
                    >
                      <SelectTrigger
                        aria-label={`Account access for ${entry.email}`}
                        className="min-w-[140px]"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="approved">Enabled</SelectItem>
                        <SelectItem value="pending">Inactive</SelectItem>
                        <SelectItem value="denied">Disabled</SelectItem>
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="space-x-2 px-3 py-3 text-right">
                    {isSelf ? (
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Signed in
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant={isDirty ? 'default' : 'outline'}
                        disabled={!isDirty || isBusy}
                        onClick={() => onUpdate(entry)}
                      >
                        Update
                      </Button>
                    )}
                    {!isSelf && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isBusy || resetDisabled}
                        onClick={() => onResetPassword(entry)}
                      >
                        Reset password
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
