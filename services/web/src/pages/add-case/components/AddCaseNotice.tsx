import type { ReactNode } from 'react';

type AddCaseNoticeProps = {
  tone: 'error' | 'loading' | 'info';
  message: string;
  icon?: ReactNode;
};

const toneStyles: Record<AddCaseNoticeProps['tone'], string> = {
  error: 'border border-destructive/40 bg-destructive/10 text-destructive font-semibold',
  loading: 'border border-border bg-muted/40 text-foreground',
  info: 'border border-border bg-muted/40 text-muted-foreground',
};

export function AddCaseNotice({ tone, message, icon }: AddCaseNoticeProps) {
  return (
    <div className={`rounded-xl px-3 py-3 ${toneStyles[tone]} ${icon ? 'flex items-center gap-3' : ''}`}>
      {icon}
      <span>{message}</span>
    </div>
  );
}
