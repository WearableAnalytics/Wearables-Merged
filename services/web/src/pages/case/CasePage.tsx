import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/custom/PageHeader';
import { defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { ResponseError } from '@/api/openapi-client/runtime';
import { InfoItem } from '@/components/custom/InfoItem';
import { useActiveCase } from '@/lib/activeCase';
import { SignedInAs } from '@/components/custom/SignedInAs';
import { CaseQrCard } from './components/CaseQrCard';
import { CaseQrModal } from './components/CaseQrModal';
import { GrafanaTileLayout, type GrafanaLayoutBlock } from './components/GrafanaTileLayout';

const GRAFANA_PROXY_URL = import.meta.env.VITE_GRAFANA_PROXY_URL;
const ONE_HOUR_MS = 60 * 60 * 1000;
const ONE_DAY_MS = 24 * ONE_HOUR_MS;

function toDatetimeLocalValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function parseDatetimeLocalValue(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function CasePage() {
  const { caseId } = useParams();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setActiveCase, clearActiveCase, activeCase } = useActiveCase();
  const [isQrOpen, setIsQrOpen] = useState(false);
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

      try {
        const caseResponse = await defaultApi.casesCaseIdGet({ caseId });
        const patientResponse = await defaultApi.patientsPatientIdGet({ patientId: caseResponse.patientId });
        const currentActiveCase = activeCaseRef.current;
        const caseToken = caseResponse.caseToken ?? currentActiveCase?.caseToken ?? null;
        const mergedCase = { ...caseResponse, caseToken };

        if (cancelled) return;

        setCaseData(mergedCase);
        setPatient(patientResponse);

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

  const formatDate = (value: Patient['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  const patientName = useMemo(
    () => (patient ? `${patient.firstName} ${patient.lastName}` : 'Case details'),
    [patient],
  );

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

    return params.toString();
  }, [caseData?.caseToken, fromInput, toInput]);

  const grafanaUrl = useMemo(() => {
    if (!GRAFANA_PROXY_URL || !grafanaBaseQuery) return null;
    return `${GRAFANA_PROXY_URL}/embed?${grafanaBaseQuery}`;
  }, [grafanaBaseQuery]);

  const grafanaLayoutBlocks = useMemo<GrafanaLayoutBlock[]>(
    () => [
      {
        type: 'section',
        title: 'Cardiovascular Health',
        description: 'This section shows key cardiovascular metrics and trends.',
      },
      {
        type: 'panel',
        panelId: 'panel-1',
        colSpan: 4,
        rowSpan: 3,
      },
      {
        type: 'panel',
        panelId: 'panel-2',
        colSpan: 2,
        rowSpan: 2,
      },
      {
        type: 'panel',
        panelId: 'panel-4',
        colSpan: 2,
        rowSpan: 1,
      },
      {
        type: 'panel',
        panelId: 'panel-3',
        colSpan: 2,
        rowSpan: 2,
      },

            {
        type: 'panel',
        panelId: 'panel-5',
        colSpan: 2,
        rowSpan: 1,
      },

      {
        type: 'panel',
        panelId: 'panel-6',
        colSpan: 4,
        rowSpan: 2,
      },

      {
        type: 'panel',
        panelId: 'panel-7',
        colSpan: 4,
        rowSpan: 2,
      },


      {
        type: 'section',
        title: 'Cardio',
        description: 'First tile rendered via the layout framework.',
      },
    ],
    [],
  );

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

      <section className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
        {error ? null : loading ? (
        <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
          <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
          Loading case…
        </div>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <InfoItem label="Patient" value={patientName} />
              <InfoItem label="Patient ID" value={patient?.patientId ?? '—'} />
              <InfoItem label="Case ID" value={caseData?.caseId ?? '—'} />
              <InfoItem label="Charité Case ID" value={caseData?.cCaseId ?? '—'} />
              <InfoItem label="Status" value={caseData?.status ?? '—'} />
              <InfoItem
                label="Date of birth"
                value={patient?.birthDate ? formatDate(patient.birthDate) : '—'}
              />
            </dl>
          </>
        )}         
         {error ? null : loading ? (
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            Loading grafana dashboard…
          </div>
        ) : (
          grafanaUrl ? (
            <div className="relative w-full space-y-3">
              <div className="rounded-xl bg-slate-50 px-3 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                  Data time range
                </p>
                <div className="mt-3 flex flex-wrap items-end gap-3">
                  <div className="min-w-[220px]">
                    <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                      Quick range
                    </span>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="ui-control-h inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-normal text-slate-700 transition hover:border-slate-300 hover:bg-slate-100"
                        onClick={() => setRangeFromNow(ONE_DAY_MS)}
                      >
                        Last 24h
                      </button>
                      <button
                        type="button"
                        className="ui-control-h inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-normal text-slate-700 transition hover:border-slate-300 hover:bg-slate-100"
                        onClick={() => setRangeFromNow(2 * ONE_DAY_MS)}
                      >
                        Last 48h
                      </button>
                      <button
                        type="button"
                        className="ui-control-h inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-normal text-slate-700 transition hover:border-slate-300 hover:bg-slate-100"
                        onClick={() => setRangeFromNow(7 * ONE_DAY_MS)}
                      >
                        Last 7d
                      </button>
                    </div>
                  </div>
                  <label className="min-w-[240px] flex-1">
                    <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                      From
                    </span>
                    <input
                      type="datetime-local"
                      className="ui-control-h mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                      value={fromInput}
                      max={toInput}
                      onChange={(event) => setFromInput(event.target.value)}
                    />
                  </label>
                  <label className="min-w-[240px] flex-1">
                    <span className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                      Till
                    </span>
                    <input
                      type="datetime-local"
                      className="ui-control-h mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
                      value={toInput}
                      min={fromInput}
                      max={toDatetimeLocalValue(new Date())}
                      onChange={(event) => setToInput(event.target.value)}
                    />
                  </label>
                </div>
              </div>
              {timeRangeError ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">
                  {timeRangeError}
                </div>
              ) : null}
              <GrafanaTileLayout
                blocks={grafanaLayoutBlocks}
                grafanaProxyUrl={GRAFANA_PROXY_URL}
                grafanaBaseQuery={grafanaBaseQuery}
              />
              <div>
                <iframe
                  title="Grafana patient monitoring dashboard"
                  src={grafanaUrl}
                  className="h-[min(80vh,1000px)] w-full rounded-xl"
                  allow="fullscreen"
                />
              </div>
            </div>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900">
              Missing case token or Grafana proxy URL. Dashboard cannot be loaded.
            </div>
          )
        )}
      </section>

      <CaseQrModal isOpen={isQrOpen} caseToken={caseData?.caseToken} onClose={() => setIsQrOpen(false)} />
    </>
  );
}
