import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AddCaseResultCard } from '@/pages/add-case/components/AddCaseResultCard';
import { SearchForm } from '@/components/custom/SearchForm';
import { defaultApi } from '@/api/defaultApi';
import type { CaseCreated, ChariteCase } from '@/api/openapi-client';
import { ResponseError } from '@/api/openapi-client/runtime';
import { PageHeader } from '@/components/custom/PageHeader';
import { useActiveCase } from '@/lib/activeCase';
import { SignedInAs } from '@/components/custom/SignedInAs';

export function AddCasePage() {
  const [caseId, setCaseId] = useState('');
  const [result, setResult] = useState<ChariteCase | null>(null);
  const [created, setCreated] = useState<CaseCreated | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const navigate = useNavigate();
  const { setActiveCase } = useActiveCase();

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'add-case-error' });
    } else {
      toast.dismiss('add-case-error');
    }
  }, [error]);

  useEffect(() => {
    if (loading) {
      toast.loading('Searching for case…', { id: 'add-case-loading' });
    } else {
      toast.dismiss('add-case-loading');
    }
  }, [loading]);

  useEffect(() => {
    if (!loading && !error && !result && hasSearched) {
      toast.info('Search for a Charité case by entering its ID above.', { id: 'add-case-empty' });
    } else {
      toast.dismiss('add-case-empty');
    }
  }, [loading, error, result, hasSearched]);

  useEffect(() => {
    if (createError) {
      toast.error(createError, { id: 'add-case-create-error' });
    } else {
      toast.dismiss('add-case-create-error');
    }
  }, [createError]);

  useEffect(() => {
    if (created) {
      toast.success('Case created.', {
        id: 'add-case-created',
        description: `Case ID: ${created.caseId} · Patient ID: ${created.patientId}`,
      });
    } else {
      toast.dismiss('add-case-created');
    }
  }, [created]);

  const formatDate = (value: ChariteCase['birthDate']) =>
    new Date(value).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });

  const resetFeedback = () => {
    setResult(null);
    setError(null);
    setCreated(null);
    setCreateError(null);
    setHasSearched(false);
  };

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedId = caseId.trim();

    if (!trimmedId) {
      setError('Please enter a Charité case ID.');
      setResult(null);
      setCreated(null);
      setCreateError(null);
      setHasSearched(false);
      return;
    }

    setHasSearched(true);
    setLoading(true);
    setError(null);
    setResult(null);
    setCreated(null);
    setCreateError(null);

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

  const handleCreate = async () => {
    if (!result?.cCaseId || creating) return;

    setCreating(true);
    setCreateError(null);
    setCreated(null);

    try {
      const data = await defaultApi.casesFromChariteCasePost({
        casesFromChariteCasePostRequest: { cCaseId: result.cCaseId },
      });
      setCreated(data);

      try {
        const [caseDetails, patientDetails] = await Promise.all([
          defaultApi.casesCaseIdGet({ caseId: data.caseId }),
          defaultApi.patientsPatientIdGet({ patientId: data.patientId }),
        ]);

        setActiveCase({
          caseData: { ...caseDetails, caseToken: caseDetails.caseToken ?? data.caseToken },
          patient: patientDetails,
        });
        navigate(`/cases/${data.caseId}`);
      } catch (hydrateError) {
        setCreateError(
          hydrateError instanceof Error ? hydrateError.message : 'Case created but failed to load details.',
        );
      }
    } catch (err) {
      if (err instanceof ResponseError) {
        setCreateError(
          err.response.status === 404 ? 'Charité case not found anymore.' : 'Unable to create internal case.',
        );
      } else if (err instanceof Error) {
        setCreateError(err.message);
      } else {
        setCreateError('Unable to create internal case.');
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <PageHeader
        label="Add Case"
        title="Add a Case"
        description="Search for an existing Charité case by ID."
      />
      <SignedInAs />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={caseId}
            loading={loading}
            onChange={(value) => setCaseId(value)}
            onFocusReset={resetFeedback}
            onSubmit={handleSearch}
            inputId="case-search"
            inputLabel="Search for a case by ID"
            inputType="search"
            inputMode="numeric"
            placeholder="Enter Charité Case ID"
          />

          <div className="mt-6 space-y-3 min-h-[240px]">
            {!loading && !error && result ? (
              <AddCaseResultCard
                caseData={result}
                creating={creating}
                formatDate={formatDate}
                onCreate={handleCreate}
              />
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
