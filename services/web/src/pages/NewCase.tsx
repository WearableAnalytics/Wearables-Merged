import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import type { ChariteCase } from '@/api/openapi-client';
import { ResponseError } from '@/api/openapi-client/runtime';
import { Loader2, Search } from 'lucide-react';

export function NewCasePage() {
  const [caseId, setCaseId] = useState('');
  const [result, setResult] = useState<ChariteCase | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const formattedBasePath = useMemo(() => API_BASE_PATH.replace(/\/$/, ''), []);

  const formatDate = (value: ChariteCase['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedId = caseId.trim();

    if (!trimmedId) {
      setError('Please enter a Charité case ID.');
      setResult(null);
      setHasSearched(false);
      return;
    }

    setHasSearched(true);
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await defaultApi.chariteCasesCCaseIdGet({ cCaseId: trimmedId });
      setResult(data);
    } catch (err) {
      if (err instanceof ResponseError) {
        setError(err.response.status === 404 ? 'No case found for that ID.' : 'Unable to fetch case.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Unable to fetch case.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        label="New Case"
        title="Create a New Case"
        description="Search for an existing Charité case by ID."
      />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <form onSubmit={handleSearch} className="space-y-4" aria-busy={loading}>
            <label className="sr-only" htmlFor="case-search">
              Search for a case by ID
            </label>
            <div className="relative flex items-center">
              <input
                id="case-search"
                type="search"
                inputMode="numeric"
                maxLength={200}
                placeholder={`Enter Charité Case ID (${formattedBasePath}/charite/cases/:id)`}
                value={caseId}
                onChange={(event) => setCaseId(event.target.value)}
                onFocus={() => {
                  setResult(null);
                  setError(null);
                  setHasSearched(false);
                }}
                className="w-full rounded-full border border-slate-200 bg-white px-6 py-4 pr-16 text-lg shadow-[0_16px_40px_rgba(15,23,42,0.08)] outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-50"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading}
                className="absolute right-2 flex h-12 w-12 items-center justify-center rounded-full bg-black text-white transition-transform duration-200 hover:scale-[1.05] focus:outline-none focus:ring-2 focus:ring-black focus:ring-offset-2 active:scale-95 disabled:opacity-80 disabled:hover:scale-100"
              >
                {loading ? <Loader2 aria-hidden className="h-5 w-5 animate-spin" /> : <Search aria-hidden className="h-5 w-5" />}
                <span className="sr-only">Search</span>
              </button>
            </div>
          </form>

          <div className="mt-6 space-y-3 min-h-[240px]">
            {error ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-3 font-semibold text-rose-700">
                {error}
              </div>
            ) : null}

            {loading ? (
              <div className="flex items-center gap-3 rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 text-slate-900">
                <Loader2 aria-hidden className="h-5 w-5 animate-spin text-slate-600" />
                <span>Searching for case…</span>
              </div>
            ) : null}

            {!loading && !error && result ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="m-0 text-sm font-semibold uppercase tracking-[0.08em] text-slate-500">
                      Charité case
                    </p>
                    <h3 className="m-0 text-[22px] font-semibold text-slate-900">
                      {result.firstName} {result.lastName}
                    </h3>
                  </div>
                  <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 font-mono text-sm tracking-[0.02em] text-slate-700">
                    ID
                    <span className="font-semibold text-slate-900">{result.cCaseId}</span>
                  </span>
                </div>

                <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 px-3 py-3">
                    <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">First name</dt>
                    <dd className="m-0 text-base text-slate-900">{result.firstName}</dd>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-3">
                    <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Last name</dt>
                    <dd className="m-0 text-base text-slate-900">{result.lastName}</dd>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-3">
                    <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Date of birth</dt>
                    <dd className="m-0 text-base text-slate-900">{formatDate(result.birthDate)}</dd>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-3 py-3">
                    <dt className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Charité Case ID</dt>
                    <dd className="m-0 text-base text-slate-900">{result.cCaseId}</dd>
                  </div>
                </dl>
              </div>
            ) : null}

            {!loading && !error && !result && hasSearched ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-slate-700">
                Search for a Charité case by entering its ID above.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
