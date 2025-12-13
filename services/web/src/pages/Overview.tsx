import { useEffect, useMemo, useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import type { Patient } from '@/api/openapi-client';

export function OverviewPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchPatients = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await defaultApi.patientsGet();
        if (!cancelled) {
          setPatients(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load patients.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchPatients();

    return () => {
      cancelled = true;
    };
  }, []);

  const formattedBasePath = useMemo(() => API_BASE_PATH.replace(/\/$/, ''), []);

  const formatDate = (value: Patient['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  return (
    <>
      <PageHeader
        label="Overview"
        title="All Patients"
        description={
          <>
            Displaying every patient returned by{' '}
            <span className="font-mono tracking-[0.01em]">{formattedBasePath}</span>
          </>
        }
      />

      <section className="bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-4 md:p-5">
        <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <h2 className="m-0 text-[22px] font-semibold">Patients</h2>
            <p className="m-0 text-slate-500">
              {loading ? 'Loading patients…' : `${patients.length} patient${patients.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>

        {error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 font-semibold text-rose-700">
            Unable to load patients: {error}
          </div>
        ) : loading ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            Loading patients…
          </div>
        ) : patients.length === 0 ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            No patients found.
          </div>
        ) : (
          <div className="overflow-auto">
            <table className="w-full border-collapse text-[15px]">
              <thead className="bg-slate-50 text-left text-slate-600 font-bold">
                <tr className="border-b border-slate-200">
                  <th className="px-3 py-3">Patient ID</th>
                  <th className="px-3 py-3">Full Name</th>
                  <th className="px-3 py-3">Date of Birth</th>
                </tr>
              </thead>
              <tbody className="text-slate-900">
                {patients.map((patient) => (
                  <tr key={patient.patientId} className="border-b last:border-b-0 border-slate-200">
                    <td className="px-3 py-3 font-mono tracking-[0.01em]">{patient.patientId}</td>
                    <td className="px-3 py-3">
                      {patient.firstName} {patient.lastName}
                    </td>
                    <td className="px-3 py-3">{formatDate(patient.birthDate)}</td>
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
