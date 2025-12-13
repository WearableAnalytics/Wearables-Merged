import type { ReactNode } from 'react';

type AddCaseNoticeProps = {
  tone: 'error' | 'loading' | 'info';
  message: string;
  icon?: ReactNode;
};

const toneStyles: Record<AddCaseNoticeProps['tone'], string> = {
  error: 'border border-rose-200 bg-rose-50 text-rose-700 font-semibold',
  loading: 'border border-sky-200 bg-sky-50 text-slate-900',
  info: 'border border-slate-200 bg-slate-50 text-slate-700',
};

export function AddCaseNotice({ tone, message, icon }: AddCaseNoticeProps) {
  return (
    <div className={`rounded-xl px-3 py-3 ${toneStyles[tone]} ${icon ? 'flex items-center gap-3' : ''}`}>
      {icon}
      <span>{message}</span>
    </div>
  );
}
