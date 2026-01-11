import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronDown, Minimize2, Maximize2 } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { SignedInAs } from '@/components/custom/SignedInAs';
import { InfoItem } from '@/components/custom/InfoItem';
import { defaultApi } from '@/api/defaultApi';
import type { Case, Patient } from '@/api/openapi-client';

// Grafana configuration
// Use the grafana-proxy backend to handle authentication with service account token
const GRAFANA_PROXY_URL = import.meta.env.VITE_GRAFANA_PROXY_URL ?? 'http://localhost:3002/grafana-sa';
const GRAFANA_DASHBOARD_ID = 'wearables-health-real';
const GRAFANA_ORG_ID = '1';
const GRAFANA_DATASOURCE = 'ff75xjfihtpmod'; // DS_INFLUXDB

// TODO: Implement Case -> DeviceId mapping when backend supports it
// Currently deviceId needs to be entered manually

export function PatientMonitoringPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();

  const [allCases, setAllCases] = useState<Case[]>([]);
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [isCardMinimized, setIsCardMinimized] = useState(false);
  const [deviceId, setDeviceId] = useState<string>(''); // Manual deviceId input

  // Fetch all cases for the dropdown
  useEffect(() => {
    const fetchCases = async () => {
      try {
        const cases = await defaultApi.casesGet();
        setAllCases(cases);
      } catch (err) {
        console.error('Failed to load cases:', err);
      }
    };
    fetchCases();
  }, []);

  // Fetch selected case and patient data
  useEffect(() => {
    if (!caseId) {
      setLoading(false);
      return;
    }

    const fetchCaseData = async () => {
      setLoading(true);
      try {
        const caseData = await defaultApi.casesCaseIdGet({ caseId });
        const patientData = await defaultApi.patientsPatientIdGet({
          patientId: caseData.patientId
        });

        setSelectedCase(caseData);
        setPatient(patientData);
      } catch (err) {
        console.error('Failed to load case data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCaseData();
  }, [caseId]);

  const grafanaUrl = useMemo(() => {
    if (!deviceId) return null;

    const params = new URLSearchParams({
      orgId: GRAFANA_ORG_ID,
      from: 'now-7d',
      to: 'now',
      timezone: 'browser',
      'var-DS_INFLUXDB': GRAFANA_DATASOURCE,
      'var-deviceId': deviceId,
    });

    return `${GRAFANA_PROXY_URL}/d/${GRAFANA_DASHBOARD_ID}/wearables-dashboard-real?${params.toString()}`;
  }, [deviceId]);

  const formatDate = (value: Patient['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  const handleCaseChange = (newCaseId: string) => {
    navigate(`/monitoring/${newCaseId}`);
  };

  return (
    <>
      <PageHeader
        label="Monitoring"
        title="Patient Monitoring"
        description="Live patient monitoring with Grafana dashboards"
      />
      <SignedInAs />

      {/* Case Selector & Device ID Input */}
      <section className="mb-4 flex flex-col gap-3 md:flex-row md:gap-4">
        {/* Case Selector */}
        <div className="relative flex-1">
          <select
            value={caseId || ''}
            onChange={(e) => handleCaseChange(e.target.value)}
            className="w-full appearance-none rounded-xl border border-slate-200 bg-white px-4 py-3 pr-10 font-medium text-slate-900 shadow-sm hover:border-slate-300 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          >
            <option value="">Select a case...</option>
            {allCases.map((c) => (
              <option key={c.caseId} value={c.caseId}>
                Case {c.caseId} - {c.cCaseId}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
        </div>

        {/* Device ID Input */}
        <div className="flex-1">
          <input
            type="text"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            placeholder="Enter Device ID (e.g., iOS_1765014596413_567510)"
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-sm text-slate-900 placeholder:text-slate-400 shadow-sm hover:border-slate-300 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          />
        </div>
      </section>

      {/* Grafana iframe */}
      {grafanaUrl ? (
        <section className="relative rounded-2xl border border-slate-200 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
          <div className="border-b border-slate-200 px-4 py-3 text-sm text-slate-500">
            <span className="font-mono text-xs">{grafanaUrl}</span>
          </div>
          <div className="relative w-full">
            <iframe
              title="Grafana patient monitoring dashboard"
              src={grafanaUrl}
              className="w-full h-[min(80vh,1000px)] rounded-b-2xl"
              allow="fullscreen"
            />
          </div>

          {/* Floating Patient Card */}
          {selectedCase && patient && !loading && (
            <div
              className={`absolute top-20 right-4 w-80 rounded-xl border border-slate-200 bg-white shadow-[0_20px_40px_rgba(15,23,42,0.15)] transition-all duration-200 ${
                isCardMinimized ? 'h-auto' : ''
              }`}
            >
              {/* Card Header */}
              <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3 rounded-t-xl">
                <h3 className="m-0 text-sm font-bold text-slate-900">Patient Info</h3>
                <button
                  onClick={() => setIsCardMinimized(!isCardMinimized)}
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200 hover:text-slate-900 transition-colors"
                  aria-label={isCardMinimized ? 'Expand card' : 'Minimize card'}
                >
                  {isCardMinimized ? (
                    <Maximize2 className="h-4 w-4" />
                  ) : (
                    <Minimize2 className="h-4 w-4" />
                  )}
                </button>
              </div>

              {/* Card Content */}
              {!isCardMinimized && (
                <div className="p-4 space-y-3">
                  <InfoItem
                    label="Patient"
                    value={`${patient.firstName} ${patient.lastName}`}
                  />
                  <InfoItem
                    label="Patient ID"
                    value={patient.patientId}
                  />
                  <InfoItem
                    label="Case ID"
                    value={selectedCase.caseId}
                  />
                  <InfoItem
                    label="Charité Case ID"
                    value={selectedCase.cCaseId ?? '—'}
                  />
                  <InfoItem
                    label="Status"
                    value={
                      <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold capitalize">
                        {selectedCase.status}
                      </span>
                    }
                  />
                  <InfoItem
                    label="Date of birth"
                    value={patient.birthDate ? formatDate(patient.birthDate) : '—'}
                  />
                </div>
              )}
            </div>
          )}
        </section>
      ) : (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-4 text-center font-semibold text-slate-900">
          Please select a case to view the monitoring dashboard.
        </div>
      )}
    </>
  );
}
