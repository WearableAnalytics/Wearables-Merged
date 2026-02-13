import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/custom/PageHeader';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { Button } from '@/components/ui/button';
import { SignedInAs } from '@/components/custom/SignedInAs';

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

  useEffect(() => {
    if (error) {
      toast.error(`Unable to load cases: ${error}`, { id: 'overview-error' });
    } else {
      toast.dismiss('overview-error');
    }
  }, [error]);

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
      <SignedInAs />

      <section className="surface-card p-4 md:p-5">
        <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <h2 className="text-section-title">Cases</h2>
            <p className="m-0 text-muted-foreground">
              {loading ? 'Loading cases…' : `${cases.length} case${cases.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>

        {error ? null : loading ? (
          <div className="surface-subtle px-3 py-3 font-semibold text-foreground">
            Loading cases…
          </div>
        ) : cases.length === 0 ? (
          <div className="surface-subtle px-3 py-3 font-semibold text-foreground">
            No cases found.
          </div>
        ) : (
          <div className="overflow-auto">
            <table className="table-grid">
              <thead className="table-head">
                <tr className="table-row">
                  <th className="px-3 py-3">Patient</th>
                  <th className="px-3 py-3">Case ID</th>
                  <th className="px-3 py-3">Patient ID</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((caseItem) => (
                  <tr key={caseItem.caseId} className="table-row last:border-b-0">
                    <td className="px-3 py-3">
                      {caseItem.patient ? (
                        <>
                          {caseItem.patient.firstName} {caseItem.patient.lastName}
                        </>
                      ) : (
                        <span className="text-muted-foreground">Unknown patient</span>
                      )}
                    </td>
                    <td className="px-3 py-3 font-mono tracking-[0.01em]">{caseItem.caseId}</td>
                    <td className="px-3 py-3 font-mono tracking-[0.01em]">{caseItem.patientId}</td>
                    <td className="px-3 py-3">
                      <span className="inline-flex items-center rounded-full border border-border bg-muted/40 px-2 py-1 text-xs font-semibold capitalize">
                        {caseItem.status}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button
                        asChild
                        size="icon"
                        searchBehavior
                        className="rounded-full"
                        aria-label={`Open case ${caseItem.caseId}`}
                      >
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
