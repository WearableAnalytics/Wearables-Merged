import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { ResponseError } from '@/api/openapi-client/runtime';
import { InfoItem } from '@/pages/add-case/components/InfoItem';
import { useActiveCase } from '@/lib/activeCase';
import QRCode from 'qrcode';

export function CasePage() {
  const { caseId } = useParams();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setActiveCase, clearActiveCase, activeCase } = useActiveCase();
  const qrCanvasRef = useRef<HTMLCanvasElement | null>(null);

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
        const caseToken = caseResponse.caseToken ?? activeCase?.caseToken ?? null;
        const mergedCase = { ...caseResponse, caseToken };

        if (cancelled) return;

        setCaseData(mergedCase);
        setPatient(patientResponse);

        const shouldUpdateActiveCase =
          !activeCase ||
          activeCase.caseId !== mergedCase.caseId ||
          activeCase.caseToken !== mergedCase.caseToken ||
          activeCase.patientId !== patientResponse.patientId;

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

  useEffect(() => {
    if (!caseData?.caseToken || !qrCanvasRef.current) return;

    const dpr = window.devicePixelRatio || 1;
    const targetSize = 110;
    const renderSize = Math.floor(targetSize * dpr);
    const canvasEl = qrCanvasRef.current;

    QRCode.toCanvas(canvasEl, caseData.caseToken, {
      width: renderSize,
      margin: 0,
      color: {
        dark: '#0f172a',
        light: '#ffffff',
      },
    })
      .then(() => {
        canvasEl.style.width = `${targetSize}px`;
        canvasEl.style.height = `${targetSize}px`;
      })
      .catch(() => {
        /* noop: keep silent if QR rendering fails */
      });
  }, [caseData?.caseToken]);

  return (
    <>
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between md:gap-6">
        <div className="flex-1">
          <PageHeader
            label="Case"
            title={patientName}
            description={caseData ? `Internal case ${caseData.caseId}` : 'Loading case…'}
          />
        </div>
        <div className="w-full md:w-auto md:max-w-[380px] md:self-start">
          <div className="w-full rounded-2xl border border-slate-200 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)] p-3 flex items-center justify-between gap-3">
            <div className="flex flex-col gap-1">
              <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Access for app</p>
              <p className="m-0 text-sm font-medium text-slate-700">Scan with Wearables app</p>
            </div>
            <div className="flex items-center">
              {caseData?.caseToken ? (
                <div className="rounded-xl bg-white p-2">
                  <canvas ref={qrCanvasRef} className="h-[110px] w-[110px]" aria-label="Case access QR code" />
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                  No token available
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
        {error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700">
            {error}
          </div>
        ) : loading ? (
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

            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
              <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Case token</p>
              <code className="mt-1 inline-block rounded-lg bg-white px-3 py-2 font-mono text-sm tracking-[0.02em] text-slate-900 shadow-sm">
                {caseData?.caseToken ?? '—'}
              </code>
            </div>
          </>
        )}
      </section>
    </>
  );
}
