import { useEffect, useMemo, useState } from 'react';
import './App.css';
import { API_BASE_PATH, defaultApi } from './api/defaultApi';
import type { Patient } from './api/openapi-client';

function App() {
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

  const formattedBasePath = useMemo(
    () => API_BASE_PATH.replace(/\/$/, ''),
    []
  );

  const formatDate = (value: Patient['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Patient Registry</p>
        <h1>All Patients</h1>
        <p className="description">
          Displaying every patient returned by <span className="mono">{formattedBasePath}</span>
        </p>
      </header>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Patients</h2>
            <p className="muted">
              {loading ? 'Loading patients…' : `${patients.length} patient${patients.length === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>

        {error ? (
          <div className="status error">Unable to load patients: {error}</div>
        ) : loading ? (
          <div className="status">Loading patients…</div>
        ) : patients.length === 0 ? (
          <div className="status">No patients found.</div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Patient ID</th>
                  <th>Full Name</th>
                  <th>Date of Birth</th>
                </tr>
              </thead>
              <tbody>
                {patients.map((patient) => (
                  <tr key={patient.patientId}>
                    <td className="mono">{patient.patientId}</td>
                    <td>{patient.firstName} {patient.lastName}</td>
                    <td>{formatDate(patient.birthDate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default App;
