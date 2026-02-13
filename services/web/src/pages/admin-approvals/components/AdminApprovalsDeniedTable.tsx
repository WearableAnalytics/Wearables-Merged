import { Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDateOrFallback } from '@/lib/date';
import { AdminApprovalsEmptyState } from './AdminApprovalsEmptyState';
import type { AdminUser } from './types';

type AdminApprovalsDeniedTableProps = {
  users: AdminUser[];
  actionUserId: string | null;
  onUnblock: (userId: string) => void;
};

export function AdminApprovalsDeniedTable({ users, actionUserId, onUnblock }: AdminApprovalsDeniedTableProps) {
  return (
    <div className="mt-4 overflow-auto">
      {users.length === 0 ? (
        <AdminApprovalsEmptyState
          title="No denied users."
          description="Denied accounts will be listed here."
          icon={<Inbox className="h-4 w-4" />}
        />
      ) : (
        <table className="table-grid">
          <thead className="table-head">
            <tr className="table-row">
              <th className="px-3 py-3">Email</th>
              <th className="px-3 py-3">Denied</th>
              <th className="px-3 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {users.map((entry) => {
              const deniedAt = formatDateOrFallback(entry.deniedAt);
              const isBusy = actionUserId === entry.id;

              return (
                <tr key={entry.id} className="table-row last:border-b-0">
                  <td className="px-3 py-3 font-medium text-foreground">{entry.email}</td>
                  <td className="px-3 py-3 text-muted-foreground">{deniedAt}</td>
                  <td className="px-3 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => onUnblock(entry.id)} disabled={isBusy}>
                      Unblock
                    </Button>
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
