import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';
import { useMessageToast } from '@/lib/toast';
import { Button } from '@/components/ui/button';

const formatBirthDate = (birthDate: Date | undefined) => {
  if (!(birthDate instanceof Date) || Number.isNaN(birthDate.getTime())) {
    return 'Unknown';
  }

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = birthDate.getUTCDate();
  const month = monthNames[birthDate.getUTCMonth()];
  const year = birthDate.getUTCFullYear();

  return `${day}. ${month} ${year}`;
};

const formatStatusLabel = (status: string) => {
  if (!status) return 'Unknown';

  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
};

const getStatusPillClassName = (status: string) => {
  const normalizedStatus = status.toLowerCase();
  const baseClassName = 'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold';

  if (normalizedStatus === 'active') {
    return `${baseClassName} border-[hsl(var(--success)/0.35)] bg-[hsl(var(--success)/0.16)] text-[hsl(var(--success))]`;
  }

  if (normalizedStatus === 'inactive') {
    return `${baseClassName} border-[hsl(var(--destructive)/0.35)] bg-[hsl(var(--destructive)/0.16)] text-[hsl(var(--destructive))]`;
  }

  return `${baseClassName} border-border bg-muted/40 text-foreground`;
};

export function OverviewPage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<(Case & { patient?: Patient })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const loadErrorToastMessage = error ? `Unable to load cases: ${error}` : null;
  useMessageToast('error', 'overview-error', loadErrorToastMessage);

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
  const statusOptions = useMemo(
    () => Array.from(new Set(cases.map((item) => item.status))).sort(),
    [cases],
  );
  const statusFilterOptions = useMemo(() => ['all', ...statusOptions], [statusOptions]);

  const filteredCases = useMemo(() => {
    const query = search.trim().toLowerCase();

    return cases.filter((caseItem) => {
      if (statusFilter !== 'all' && caseItem.status !== statusFilter) {
        return false;
      }

      if (!query) return true;

      const patientName =
        caseItem.patient ? `${caseItem.patient.firstName} ${caseItem.patient.lastName}`.toLowerCase() : '';
      const hospitalCaseId = (caseItem.hospitalCaseId ?? '').toLowerCase();

      return patientName.includes(query) || hospitalCaseId.includes(query);
    });
  }, [cases, search, statusFilter]);

  return (
    <>
      <PageHeader
        label="Overview"
        title="All Patients"
        description={
          <>
            Displaying every patient case returned by{' '}
            <span className="font-mono tracking-[0.01em]">{formattedBasePath}</span>
          </>
        }
      />

      <section className="surface-card p-4 md:p-5">
        <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="shrink-0">
            <h2 className="text-section-title">Patients</h2>
            <p className="m-0 text-muted-foreground">
              {loading ? 'Loading patients…' : `${filteredCases.length} result${filteredCases.length === 1 ? '' : 's'}`}
            </p>
          </div>

          <div className="flex flex-1 flex-col gap-3 md:flex-row md:items-center md:justify-end">
            <input
              type="search"
              placeholder="Search by patient name or Hospital case ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="field-input h-[calc(var(--ui-control-height)+0.5rem)] rounded-full px-4 w-full md:w-[20rem] md:min-w-[18rem]"
            />

            <div className="inline-flex max-w-full flex-wrap gap-2 rounded-xl border border-border bg-muted/40 p-1 md:justify-end">
              {statusFilterOptions.map((status) => {
                const isActive = statusFilter === status;

                return (
                  <Button
                    key={status}
                    size="sm"
                    variant={isActive ? 'default' : 'ghost'}
                    className="px-3"
                    aria-pressed={isActive}
                    onClick={() => setStatusFilter(status)}
                  >
                    {status === 'all' ? 'All statuses' : formatStatusLabel(status)}
                  </Button>
                );
              })}
            </div>
          </div>
        </div>

        {error ? null : loading ? (
          <div className="surface-subtle px-3 py-3 font-semibold text-foreground">
            Loading patients…
          </div>
        ) : filteredCases.length === 0 ? (
          <div className="surface-subtle px-3 py-3 font-semibold text-foreground">
            No patients match your filters.
          </div>
        ) : (
          <div className="overflow-auto">
            <table className="table-grid table-fixed">
              <colgroup>
                <col className="w-[22.5%]" />
                <col className="w-[22.5%]" />
                <col className="w-[22.5%]" />
                <col className="w-[22.5%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead className="table-head">
                <tr className="table-row">
                  <th className="px-3 py-3">Patient</th>
                  <th className="px-3 py-3">Hospital case ID</th>
                  <th className="px-3 py-3">Birthdate</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((caseItem) => (
                  <tr key={caseItem.caseId} className="table-row last:border-b-0">
                    <td className="px-3 py-3">
                      {caseItem.patient ? (
                        <span className="block truncate" title={`${caseItem.patient.firstName} ${caseItem.patient.lastName}`}>
                          {caseItem.patient.firstName} {caseItem.patient.lastName}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">Unknown patient</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {caseItem.hospitalCaseId ? (
                        <span className="block truncate" title={caseItem.hospitalCaseId}>
                          {caseItem.hospitalCaseId}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">Unknown</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <span className="block truncate">{formatBirthDate(caseItem.patient?.birthDate)}</span>
                    </td>
                    <td className="px-3 py-3">
                      <span className={getStatusPillClassName(caseItem.status)}>
                        {formatStatusLabel(caseItem.status)}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button
                        size="icon"
                        variant="search"
                        press
                        className="rounded-full"
                        aria-label={`Open case ${caseItem.caseId}`}
                        onClick={() => {
                          void navigate(`/cases/${caseItem.caseId}`);
                        }}
                      >
                        <ArrowRight aria-hidden className="h-4 w-4" />
                        <span className="sr-only">Open case {caseItem.caseId}</span>
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
