import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ChevronDown, ChevronRight, ChevronUp, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/custom/PageHeader';
import { defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { ResponseError } from '@/api/openapi-client/runtime';
import { Button } from '@/components/ui/button';
import { InfoItem } from '@/components/custom/InfoItem';
import { useActiveCase } from '@/lib/activeCase';
import { SignedInAs } from '@/components/custom/SignedInAs';
import { useTheme } from '@/context/ThemeContext';
import { formatDateDayMonthYear } from '@/lib/date';
import { CaseQrCard } from './components/CaseQrCard';
import { CaseQrModal } from './components/CaseQrModal';

const GRAFANA_PROXY_URL = import.meta.env.VITE_GRAFANA_PROXY_URL;
const ONE_HOUR_MS = 60 * 60 * 1000;
const ONE_DAY_MS = 24 * ONE_HOUR_MS;
const QUICK_RANGE_OPTIONS: Array<{ label: string; durationMs: number }> = [
  { label: 'Last 24h', durationMs: ONE_DAY_MS },
  { label: 'Last 48h', durationMs: 2 * ONE_DAY_MS },
  { label: 'Last 7d', durationMs: 7 * ONE_DAY_MS },
];
type RawSectionData = Record<string, unknown>;

function toDatetimeLocalValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function parseDatetimeLocalValue(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatFieldLabel(fieldKey: string): string {
  return fieldKey
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b(id|url|api|jwt)\b/gi, (match) => match.toUpperCase())
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\w/, (char) => char.toUpperCase());
}

function formatFieldValue(value: unknown, fieldKey: string): string {
  if (value === null || value === undefined) return '—';

  if (value instanceof Date) {
    return formatDateDayMonthYear(value);
  }

  if (typeof value === 'string') {
    if (value.trim().length === 0) return '—';

    if (fieldKey.toLowerCase().includes('date')) {
      const parsedDate = new Date(value);
      if (!Number.isNaN(parsedDate.getTime())) {
        return formatDateDayMonthYear(parsedDate);
      }
    }

    return value;
  }

  if (typeof value === 'number' || typeof value === 'bigint') {
    return String(value);
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (Array.isArray(value)) {
    return value.length > 0 ? value.map((item) => formatFieldValue(item, fieldKey)).join(', ') : '—';
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function toDisplayItems(sectionData: RawSectionData | null) {
  if (!sectionData) return [];

  return Object.entries(sectionData)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => ({
      key,
      label: formatFieldLabel(key),
      value: formatFieldValue(value, key),
    }));
}

export function CasePage() {
  const { caseId } = useParams();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [caseDetails, setCaseDetails] = useState<RawSectionData | null>(null);
  const [patientDetails, setPatientDetails] = useState<RawSectionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setActiveCase, clearActiveCase, activeCase } = useActiveCase();
  const [isQrOpen, setIsQrOpen] = useState(false);
  const [isDataPanelCollapsedMobile, setIsDataPanelCollapsedMobile] = useState(false);
  const [isPatientSectionCollapsed, setIsPatientSectionCollapsed] = useState(false);
  const [isCaseSectionCollapsed, setIsCaseSectionCollapsed] = useState(false);
  const { isDark } = useTheme();
  const activeCaseRef = useRef(activeCase);
  const [toInput, setToInput] = useState<string>(() => toDatetimeLocalValue(new Date()));
  const [fromInput, setFromInput] = useState<string>(() =>
    toDatetimeLocalValue(new Date(Date.now() - ONE_DAY_MS)),
  );

  useEffect(() => {
    activeCaseRef.current = activeCase;
  }, [activeCase]);

  useEffect(() => {
    let cancelled = false;

    const fetchCase = async () => {
      if (!caseId) {
        setError('No case ID provided.');
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      setCaseData(null);
      setPatient(null);
      setCaseDetails(null);
      setPatientDetails(null);

      try {
        const caseResponseRaw = await defaultApi.casesCaseIdGetRaw({ caseId });
        const caseResponseJson = (await caseResponseRaw.raw.clone().json()) as RawSectionData;
        const caseResponse = await caseResponseRaw.value();
        const patientResponseRaw = await defaultApi.patientsPatientIdGetRaw({ patientId: caseResponse.patientId });
        const patientResponseJson = (await patientResponseRaw.raw.clone().json()) as RawSectionData;
        const patientResponse = await patientResponseRaw.value();
        const currentActiveCase = activeCaseRef.current;
        const caseToken = caseResponse.caseToken ?? currentActiveCase?.caseToken ?? null;
        const mergedCase = { ...caseResponse, caseToken };

        if (cancelled) return;

        setCaseData(mergedCase);
        setPatient(patientResponse);
        setCaseDetails(caseResponseJson);
        setPatientDetails(patientResponseJson);

        const shouldUpdateActiveCase =
          !currentActiveCase ||
          currentActiveCase.caseId !== mergedCase.caseId ||
          currentActiveCase.caseToken !== mergedCase.caseToken ||
          currentActiveCase.patientId !== patientResponse.patientId;

        if (shouldUpdateActiveCase) {
          setActiveCase({ caseData: mergedCase, patient: patientResponse });
        }
      } catch (err) {
        if (cancelled) return;

        if (err instanceof ResponseError && err.response.status === 404) {
          setError('Case not found.');
        } else {
          setError(err instanceof Error ? err.message : 'Unable to load case.');
        }

        clearActiveCase();
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchCase();

    return () => {
      cancelled = true;
    };
  }, [caseId, setActiveCase, clearActiveCase]);

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'case-error' });
    } else {
      toast.dismiss('case-error');
    }
  }, [error]);

  const patientName = useMemo(() => {
    if (!patient) return 'Case details';
    const fullName = [patient.firstName, patient.lastName].filter(Boolean).join(' ').trim();
    return fullName || 'Case details';
  }, [patient]);

  const patientDisplayItems = useMemo(() => toDisplayItems(patientDetails), [patientDetails]);
  const caseDisplayItems = useMemo(() => toDisplayItems(caseDetails), [caseDetails]);

  const timeRangeError = useMemo(() => {
    const from = parseDatetimeLocalValue(fromInput);
    const to = parseDatetimeLocalValue(toInput);
    if (!from || !to) return 'Please select a valid date and time range.';
    if (from.getTime() >= to.getTime()) return '"From" must be earlier than "To".';
    return null;
  }, [fromInput, toInput]);

  const setRangeFromNow = (durationMs: number) => {
    const now = new Date();
    const from = new Date(now.getTime() - durationMs);
    setToInput(toDatetimeLocalValue(now));
    setFromInput(toDatetimeLocalValue(from));
  };

  const grafanaBaseQuery = useMemo(() => {
    const caseToken = caseData?.caseToken?.trim();
    if (!caseToken) return null;

    const params = new URLSearchParams({
      deviceId: caseToken,
    });

    const from = parseDatetimeLocalValue(fromInput);
    const to = parseDatetimeLocalValue(toInput);
    if (from && to && from.getTime() < to.getTime()) {
      params.set('from', String(from.getTime()));
      params.set('to', String(to.getTime()));
    }
    if (isDark) {
      params.set('theme', 'dark');
    }

    return params.toString();
  }, [caseData?.caseToken, fromInput, isDark, toInput]);

  const grafanaUrl = useMemo(() => {
    if (!GRAFANA_PROXY_URL || !grafanaBaseQuery) return null;
    return `${GRAFANA_PROXY_URL}/embed?${grafanaBaseQuery}`;
  }, [grafanaBaseQuery]);

  return (
    <>
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between md:gap-6">
        <div className="flex-1">
          <PageHeader
            label="Case"
            title={patientName}
            description={caseData ? `Internal case ${caseData.caseId}` : 'Loading case…'}
          />
        </div>
        <div className="w-full md:w-auto md:max-w-[380px] md:self-center">
          <CaseQrCard caseToken={caseData?.caseToken} onOpen={() => setIsQrOpen(true)} />
        </div>
      </div>
      <SignedInAs />

      <section className="grid grid-cols-1 gap-4 md:grid-cols-4 md:items-start">
        <aside className="surface-card p-4 md:col-span-1">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-section-title">Case Data</h2>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="md:hidden"
              aria-expanded={!isDataPanelCollapsedMobile}
              onClick={() => setIsDataPanelCollapsedMobile((prev) => !prev)}
            >
              {isDataPanelCollapsedMobile ? 'Expand' : 'Collapse'}
              {isDataPanelCollapsedMobile ? (
                <ChevronDown aria-hidden className="h-4 w-4" />
              ) : (
                <ChevronUp aria-hidden className="h-4 w-4" />
              )}
            </Button>
          </div>

          <div className={`${isDataPanelCollapsedMobile ? 'hidden md:block' : 'block'} mt-3 space-y-4`}>
            {error ? (
              <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
                {error}
              </div>
            ) : loading ? (
              <div className="surface-subtle flex items-center gap-2 px-3 py-2 text-sm font-semibold text-muted-foreground">
                <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
                Loading case…
              </div>
            ) : (
              <>
                <div>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    aria-expanded={!isPatientSectionCollapsed}
                    onClick={() => setIsPatientSectionCollapsed((prev) => !prev)}
                  >
                    <ChevronRight
                      aria-hidden
                      className={`h-4 w-4 transition-transform ${isPatientSectionCollapsed ? '' : 'rotate-90'}`}
                    />
                    <span>Patient</span>
                  </button>
                  {isPatientSectionCollapsed ? null : patientDisplayItems.length === 0 ? (
                    <div className="surface-subtle mt-2 px-3 py-2 text-sm text-muted-foreground">
                      No patient fields available.
                    </div>
                  ) : (
                    <dl className="mt-2 grid grid-cols-1 gap-3">
                      {patientDisplayItems.map((item) => (
                        <InfoItem key={`patient-${item.key}`} label={item.label} value={item.value} />
                      ))}
                    </dl>
                  )}
                </div>

                <div>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    aria-expanded={!isCaseSectionCollapsed}
                    onClick={() => setIsCaseSectionCollapsed((prev) => !prev)}
                  >
                    <ChevronRight
                      aria-hidden
                      className={`h-4 w-4 transition-transform ${isCaseSectionCollapsed ? '' : 'rotate-90'}`}
                    />
                    <span>Case</span>
                  </button>
                  {isCaseSectionCollapsed ? null : caseDisplayItems.length === 0 ? (
                    <div className="surface-subtle mt-2 px-3 py-2 text-sm text-muted-foreground">
                      No case fields available.
                    </div>
                  ) : (
                    <dl className="mt-2 grid grid-cols-1 gap-3">
                      {caseDisplayItems.map((item) => (
                        <InfoItem key={`case-${item.key}`} label={item.label} value={item.value} />
                      ))}
                    </dl>
                  )}
                </div>
              </>
            )}
          </div>
        </aside>

        <div className="surface-card p-4 md:col-span-3">
          {error ? (
            <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
              {error}
            </div>
          ) : loading ? (
            <div className="surface-subtle flex items-center gap-2 px-3 py-2 text-sm font-semibold text-muted-foreground">
              <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
              Loading grafana dashboard…
            </div>
          ) : (
            grafanaUrl ? (
              <div className="relative w-full space-y-3">
                <div className="surface-subtle px-3 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Data time range
                  </p>
                  <div className="mt-3 flex flex-wrap items-end gap-3">
                    <div className="min-w-[220px]">
                      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Quick range
                      </span>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {QUICK_RANGE_OPTIONS.map((option) => (
                          <Button
                            key={option.label}
                            type="button"
                            size="sm"
                            variant="outline"
                            className="px-3 font-normal"
                            onClick={() => setRangeFromNow(option.durationMs)}
                          >
                            {option.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                    <label className="min-w-[240px] flex-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        From
                      </span>
                      <input
                        type="datetime-local"
                        className="field-input ui-control-h mt-2 w-full"
                        value={fromInput}
                        max={toInput}
                        onChange={(event) => setFromInput(event.target.value)}
                      />
                    </label>
                    <label className="min-w-[240px] flex-1">
                      <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                        Till
                      </span>
                      <input
                        type="datetime-local"
                        className="field-input ui-control-h mt-2 w-full"
                        value={toInput}
                        min={fromInput}
                        max={toDatetimeLocalValue(new Date())}
                        onChange={(event) => setToInput(event.target.value)}
                      />
                    </label>
                  </div>
                </div>
                {timeRangeError ? (
                  <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
                    {timeRangeError}
                  </div>
                ) : null}
                <iframe
                  title="Grafana patient monitoring dashboard"
                  src={grafanaUrl}
                  // Cross-origin iframes cannot be auto-sized reliably from parent page.
                  className="h-[600px] md:h-[800px] lg:h-[1000px] w-full rounded-xl"
                  allow="fullscreen"
                />
              </div>
            ) : (
              <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
                Missing case token or Grafana proxy URL. Dashboard cannot be loaded.
              </div>
            )
          )}
        </div>
      </section>

      <CaseQrModal isOpen={isQrOpen} caseToken={caseData?.caseToken} onClose={() => setIsQrOpen(false)} />
    </>
  );
}
