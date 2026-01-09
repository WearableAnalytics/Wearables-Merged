import type { ReactNode } from 'react';

type InfoItemProps = {
  label: string;
  value: ReactNode;
};

export function InfoItem({ label, value }: InfoItemProps) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">{label}</dt>
      <dd className="m-0 text-base text-slate-900">{value}</dd>
    </div>
  );
}
