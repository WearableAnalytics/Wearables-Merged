import type { ReactNode } from 'react';

type AdminApprovalsEmptyStateProps = {
  title: string;
  description?: string;
  icon?: ReactNode;
};

export function AdminApprovalsEmptyState({ title, description, icon }: AdminApprovalsEmptyStateProps) {
  return (
    <div className="surface-subtle mt-3 border-dashed px-4 py-3 text-sm text-muted-foreground">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-full bg-card p-1 text-muted-foreground ring-1 ring-inset ring-border/40">
          {icon}
        </div>
        <div>
          <p className="font-medium text-foreground">{title}</p>
          {description ? <p className="mt-1 text-muted-foreground">{description}</p> : null}
        </div>
      </div>
    </div>
  );
}
