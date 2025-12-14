import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { Button } from '@/components/ui/button';

export function OverviewPage() {
  const [cases, setCases] = useState<(Case & { patient?: Patient })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchCases = async () => {
      setLoading(true);
      setError(null);

      try {
        const [casesData, patientsData] = await Promise.all([defaultApi.casesGet(), defaultApi.patientsGet()]);

        if (cancelled) return;

        const patientMap = new Map(patientsData.map((patient) => [patient.patientId, patient]));
        const merged = casesData.map((caseItem) => ({
          ...caseItem,
          patient: patientMap.get(caseItem.patientId),
        }));

        if (!cancelled) {
          setCases(merged);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load cases.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchCases();

    return () => {
      cancelled = true;
    };
  }, []);

  const formattedBasePath = useMemo(() => API_BASE_PATH.replace(/\/$/, ''), []);

  return (
    <>
      <PageHeader
        label="Overview"
        title="All Cases"
        description={
          <>
            Displaying every case returned by{' '}
            <span className="font-mono tracking-[0.01em]">{formattedBasePath}</span>
          </>
        }
      />

      <section className="bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-4 md:p-5">
        <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <h2 className="m-0 text-[22px] font-semibold">Cases</h2>
            <p className="m-0 text-slate-500">
              {loading ? 'Loading cases…' : `${cases.length} case${cases.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>

        {error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 font-semibold text-rose-700">
            Unable to load cases: {error}
          </div>
        ) : loading ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            Loading cases…
          </div>
        ) : cases.length === 0 ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            No cases found.
          </div>
        ) : (
          <div className="overflow-auto">
            <table className="w-full border-collapse text-[15px]">
              <thead className="bg-slate-50 text-left text-slate-600 font-bold">
                <tr className="border-b border-slate-200">
                  <th className="px-3 py-3">Patient</th>
                  <th className="px-3 py-3">Case ID</th>
                  <th className="px-3 py-3">Patient ID</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="">
                {cases.map((caseItem) => (
                  <tr key={caseItem.caseId} className="border-b last:border-b-0 border-slate-200">
                    <td className="px-3 py-3">
                      {caseItem.patient ? (
                        <>
                          {caseItem.patient.firstName} {caseItem.patient.lastName}
                        </>
                      ) : (
                        <span className="text-slate-500">Unknown patient</span>
                      )}
                    </td>
                    <td className="px-3 py-3 font-mono tracking-[0.01em]">{caseItem.caseId}</td>
                    <td className="px-3 py-3 font-mono tracking-[0.01em]">{caseItem.patientId}</td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold capitalize">
                        {caseItem.status}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button asChild 
                      size="icon" 
                      className="rounded-full active:scale-50 disabled:hover:scale-100" 
                      aria-label={`Open case ${caseItem.caseId}`}>
                        <Link to={`/cases/${caseItem.caseId}`}>
                          <ArrowRight aria-hidden className="h-4 w-4" />
                          <span className="sr-only">Open case {caseItem.caseId}</span>
                        </Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
