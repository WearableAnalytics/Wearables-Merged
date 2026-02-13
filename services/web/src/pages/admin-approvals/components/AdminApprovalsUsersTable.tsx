import { Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AdminApprovalsEmptyState } from './AdminApprovalsEmptyState';
import type { AdminUser, UserDraft, UserDraftEdits, UserRole, UserStatus } from './types';

type AdminApprovalsUsersTableProps = {
  users: AdminUser[];
  currentUserId?: string;
  actionUserId: string | null;
  draftEdits: UserDraftEdits;
  onDraftUpdate: (entry: AdminUser, updates: Partial<UserDraft>) => void;
  onUpdate: (entry: AdminUser) => void;
};

export function AdminApprovalsUsersTable({
  users,
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
              <th className="px-3 py-3">Role</th>
              <th className="px-3 py-3">Access</th>
              <th className="px-3 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {users.map((entry) => {
              const isSelf = currentUserId === entry.id;
              const currentRole = (entry.role ?? 'user') as UserRole;
              const currentStatus = (entry.status ?? 'approved') as UserStatus;
              const draft = draftEdits[entry.id] ?? { role: currentRole, status: currentStatus };
              const isDirty = draft.role !== currentRole || draft.status !== currentStatus;
              const isBusy = actionUserId === entry.id;

              return (
                <tr key={entry.id} className="table-row last:border-b-0">
                  <td className="px-3 py-3 font-medium text-foreground">{entry.email}</td>
                  <td className="px-3 py-3">
                    <select
                      value={draft.role}
                      onChange={(event) => onDraftUpdate(entry, { role: event.target.value as UserRole })}
                      disabled={isSelf || isBusy}
                      className="field-input w-full min-w-[120px] rounded-md bg-card px-2 py-1"
                    >
                      <option value="admin">Admin</option>
                      <option value="user">User</option>
                    </select>
                  </td>
                  <td className="px-3 py-3">
                    <select
                      value={draft.status}
                      onChange={(event) => onDraftUpdate(entry, { status: event.target.value as UserStatus })}
                      disabled={isSelf || isBusy}
                      className="field-input w-full min-w-[140px] rounded-md bg-card px-2 py-1"
                    >
                      <option value="approved">Approved</option>
                      <option value="pending">Pending</option>
                      <option value="denied">Denied</option>
                    </select>
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
