import type { FormEvent } from 'react';
import { useState } from 'react';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { defaultApi } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';
import { ArrowRight, Loader2 } from 'lucide-react';

export function RegisterPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const resetFeedback = () => {
    setError(null);
    setMessage(null);
  };

  const handleRegister = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      setMessage(null);
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const data = await defaultApi.register(trimmedEmail);
      const successMessage =
        (data as { message?: string }).message ?? 'Your account is awaiting admin approval.';
      setMessage(successMessage);
      window.dispatchEvent(new Event('auth-change'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to register.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        label="Register"
        title="Request access"
        description="Enter your email to request access. You will be notified after approval."
      />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={email}
            loading={loading}
            onChange={(value) => setEmail(value)}
            onFocusReset={resetFeedback}
            onSubmit={handleRegister}
            inputId="register-email"
            inputLabel="Email address"
            inputType="email"
            inputMode="email"
            autoComplete="email"
            placeholder="Enter your email address"
            submitIcon={<ArrowRight aria-hidden className="h-5 w-5" />}
            submitLabel="Request access"
          />

          <div className="mt-6 space-y-3 min-h-[120px]">
            {error ? <AddCaseNotice tone="error" message={error} /> : null}

            {loading ? (
              <AddCaseNotice
                tone="loading"
                icon={<Loader2 aria-hidden className="h-5 w-5 animate-spin text-slate-600" />}
                message="Submitting access request…"
              />
            ) : null}

            {!loading && message ? <AddCaseNotice tone="info" message={message} /> : null}
          </div>
        </div>
      </div>
    </>
  );
}
