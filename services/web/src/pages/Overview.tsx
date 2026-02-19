import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpDown } from 'lucide-react';
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

type SortKey = 'patientFirstName' | 'patientLastName' | 'hospitalCaseId' | 'birthDate';
type SortDirection = 'asc' | 'desc';

export function OverviewPage() {
  const navigate = useNavigate();
  const [cases, setCases] = useState<(Case & { patient?: Patient })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortKey, setSortKey] = useState<SortKey>('patientLastName');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
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

  const sortedCases = useMemo(() => {
    const compareText = (left: string, right: string) =>
      left.localeCompare(right, undefined, { sensitivity: 'base', numeric: true });

    return [...filteredCases].sort((leftCase, rightCase) => {
      if (sortKey === 'patientFirstName' || sortKey === 'patientLastName') {
        const leftLastName = (leftCase.patient?.lastName ?? '').trim();
        const rightLastName = (rightCase.patient?.lastName ?? '').trim();
        const leftFirstName = (leftCase.patient?.firstName ?? '').trim();
        const rightFirstName = (rightCase.patient?.firstName ?? '').trim();

        const firstNameComparison = compareText(leftFirstName, rightFirstName);
        const lastNameComparison = compareText(leftLastName, rightLastName);
        const directionMultiplier = sortDirection === 'asc' ? 1 : -1;

        if (sortKey === 'patientFirstName') {
          if (firstNameComparison !== 0) return firstNameComparison * directionMultiplier;
          if (lastNameComparison !== 0) return lastNameComparison * directionMultiplier;
        } else {
          if (lastNameComparison !== 0) return lastNameComparison * directionMultiplier;
          if (firstNameComparison !== 0) return firstNameComparison * directionMultiplier;
        }

        return compareText(leftCase.caseId, rightCase.caseId);
      }

      if (sortKey === 'hospitalCaseId') {
        const leftHospitalCaseId = (leftCase.hospitalCaseId ?? '').trim();
        const rightHospitalCaseId = (rightCase.hospitalCaseId ?? '').trim();
        const hospitalCaseComparison = compareText(leftHospitalCaseId, rightHospitalCaseId);
        const directionMultiplier = sortDirection === 'asc' ? 1 : -1;

        if (hospitalCaseComparison !== 0) return hospitalCaseComparison * directionMultiplier;

        return compareText(leftCase.caseId, rightCase.caseId);
      }

      const leftBirthTimestamp = leftCase.patient?.birthDate?.getTime();
      const rightBirthTimestamp = rightCase.patient?.birthDate?.getTime();
      const leftHasBirthDate = typeof leftBirthTimestamp === 'number' && Number.isFinite(leftBirthTimestamp);
      const rightHasBirthDate = typeof rightBirthTimestamp === 'number' && Number.isFinite(rightBirthTimestamp);

      if (!leftHasBirthDate && !rightHasBirthDate) {
        return compareText(leftCase.caseId, rightCase.caseId);
      }

      if (!leftHasBirthDate) return 1;
      if (!rightHasBirthDate) return -1;

      const birthDateComparison = leftBirthTimestamp - rightBirthTimestamp;
      const directionMultiplier = sortDirection === 'asc' ? 1 : -1;

      if (birthDateComparison !== 0) return birthDateComparison * directionMultiplier;

      return compareText(leftCase.caseId, rightCase.caseId);
    });
  }, [filteredCases, sortDirection, sortKey]);

  const handleSortClick = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((currentDirection) => (currentDirection === 'asc' ? 'desc' : 'asc'));
      return;
    }

    setSortKey(key);
    setSortDirection('asc');
  };

  const renderSortIcon = (key: SortKey) => {
    if (sortKey !== key) return <ArrowUpDown aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />;
    if (sortDirection === 'asc') return <ArrowUp aria-hidden className="h-3.5 w-3.5" />;
    return <ArrowDown aria-hidden className="h-3.5 w-3.5" />;
  };

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
                <col className="w-[16%]" />
                <col className="w-[16%]" />
                <col className="w-[20%]" />
                <col className="w-[18%]" />
                <col className="w-[20%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead className="table-head">
                <tr className="table-row">
                  <th className="px-3 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-foreground/80"
                      onClick={() => handleSortClick('patientFirstName')}
                      aria-label={`Sort by first name ${sortKey === 'patientFirstName' && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                    >
                      First name
                      {renderSortIcon('patientFirstName')}
                    </button>
                  </th>
                  <th className="px-3 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-foreground/80"
                      onClick={() => handleSortClick('patientLastName')}
                      aria-label={`Sort by patient last name ${sortKey === 'patientLastName' && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                    >
                      Last name
                      {renderSortIcon('patientLastName')}
                    </button>
                  </th>
                  <th className="px-3 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-foreground/80"
                      onClick={() => handleSortClick('hospitalCaseId')}
                      aria-label={`Sort by hospital case ID ${sortKey === 'hospitalCaseId' && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                    >
                      Hospital case ID
                      {renderSortIcon('hospitalCaseId')}
                    </button>
                  </th>
                  <th className="px-3 py-3">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-semibold text-foreground hover:text-foreground/80"
                      onClick={() => handleSortClick('birthDate')}
                      aria-label={`Sort by birthdate ${sortKey === 'birthDate' && sortDirection === 'asc' ? 'descending' : 'ascending'}`}
                    >
                      Birthdate
                      {renderSortIcon('birthDate')}
                    </button>
                  </th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3 text-right">Details</th>
                </tr>
              </thead>
              <tbody>
                {sortedCases.map((caseItem) => (
                  <tr key={caseItem.caseId} className="table-row last:border-b-0">
                    <td className="px-3 py-3">
                      {caseItem.patient ? (
                        <span className="block truncate" title={caseItem.patient.firstName}>
                          {caseItem.patient.firstName}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">Unknown</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      {caseItem.patient ? (
                        <span className="block truncate" title={caseItem.patient.lastName}>
                          {caseItem.patient.lastName}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">Unknown</span>
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
