import type { ReactNode } from 'react';

type InfoItemProps = {
  label: string;
  value: ReactNode;
};

export function InfoItem({ label, value }: InfoItemProps) {
  return (
    <div className="surface-subtle px-3 py-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</dt>
      <dd className="m-0 text-base text-foreground">{value}</dd>
    </div>
  );
}
