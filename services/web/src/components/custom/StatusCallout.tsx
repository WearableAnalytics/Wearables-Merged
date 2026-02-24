import { AlertTriangle, Check, Info, OctagonX } from 'lucide-react';
import { cn } from '@/lib/utils';

export type StatusTone = 'success' | 'info' | 'warning' | 'error';

type StatusCalloutProps = {
  tone: StatusTone;
  message: string;
  className?: string;
};

const toneTokens: Record<StatusTone, string> = {
  success: '--success',
  info: '--info',
  warning: '--warning',
  error: '--destructive',
};

const toneIcons = {
  success: Check,
  info: Info,
  warning: AlertTriangle,
  error: OctagonX,
} as const;

const toToneColor = (token: string, opacity?: number) =>
  opacity === undefined ? `hsl(var(${token}))` : `hsl(var(${token}) / ${opacity})`;

export function StatusCallout({ tone, message, className }: StatusCalloutProps) {
  const toneToken = toneTokens[tone];
  const borderColor = toToneColor(toneToken, 0.35);
  const containerBackground = toToneColor(toneToken, 0.16);
  const iconBackground = toToneColor(toneToken, 0.2);
  const textColor = toToneColor(toneToken);
  const Icon = toneIcons[tone];

  return (
    <div
      className={cn('rounded-2xl border px-4 py-4', className)}
      style={{ borderColor, backgroundColor: containerBackground }}
    >
      <div className="flex items-center gap-3">
        <span
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          style={{ color: textColor, backgroundColor: iconBackground, boxShadow: `inset 0 0 0 1px ${borderColor}` }}
        >
          <Icon aria-hidden className="h-4 w-4" />
        </span>
        <p className="m-0 text-base leading-6" style={{ color: textColor }}>
          {message}
        </p>
      </div>
    </div>
  );
}
