const DAY_MONTH_YEAR_FORMATTER = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

export function formatDateDayMonthYear(value: string | number | Date): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return DAY_MONTH_YEAR_FORMATTER.format(date);
}

export function formatDateOrFallback(value?: string | null, fallback = '—'): string {
  if (!value) return fallback;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;

  return date.toLocaleDateString();
}
