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

const GRAFANA_PROXY_URL = import.meta.env.VITE_GRAFANA_PROXY_URL;

export function CasePage() {
  const { caseId } = useParams();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setActiveCase, clearActiveCase, activeCase } = useActiveCase();
  const [isQrOpen, setIsQrOpen] = useState(false);
  const activeCaseRef = useRef(activeCase);

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

  const grafanaUrl = useMemo(() => {
    const caseToken = caseData?.caseToken?.trim();
    if (!caseToken) return null;
    if (!GRAFANA_PROXY_URL) return null;

    const params = new URLSearchParams({
      deviceId: caseToken,
    });

    return `${GRAFANA_PROXY_URL}/embed?${params.toString()}`;
  }, [caseData?.caseToken]);

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
            <div className="relative w-full">
              <iframe
                title="Grafana patient monitoring dashboard"
                src={grafanaUrl}
                className="h-[min(80vh,1000px)] w-full rounded-xl"
                allow="fullscreen"
              />
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
