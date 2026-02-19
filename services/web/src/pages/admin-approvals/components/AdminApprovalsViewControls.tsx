import { Button } from '@/components/ui/button';
import type { ViewMode } from './types';

type AdminApprovalsViewControlsProps = {
  loading: boolean;
  approvedUsersCount: number;
  view: ViewMode;
  onViewChange: (view: ViewMode) => void;
  search: string;
  onSearchChange: (value: string) => void;
};

export function AdminApprovalsViewControls({
  loading,
  approvedUsersCount,
  view,
  onViewChange,
  search,
  onSearchChange,
}: AdminApprovalsViewControlsProps) {
  return (
    <>
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-section-title">Admin console</h2>
          <p className="m-0 text-muted-foreground">{loading ? 'Loading data…' : `${approvedUsersCount} users`}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={view === 'requests' ? 'default' : 'outline'}
            onClick={() => onViewChange('requests')}
          >
            Requests
          </Button>
          <Button size="sm" variant={view === 'users' ? 'default' : 'outline'} onClick={() => onViewChange('users')}>
            Current users
          </Button>
          <Button
            size="sm"
            variant={view === 'denied' ? 'default' : 'outline'}
            onClick={() => onViewChange('denied')}
          >
            Denied users
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <input
          type="search"
          placeholder="Search by email or name"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          className="field-input w-full md:max-w-xs"
        />
      </div>
    </>
  );
}
