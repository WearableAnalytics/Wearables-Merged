import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { defaultApi } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';
import { ArrowRight, Loader2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const resetFeedback = () => {
    setError(null);
    setMessage(null);
  };

  useEffect(() => {
    if (!authLoading && user) {
      navigate('/overview', { replace: true });
    }
  }, [user, authLoading, navigate]);

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      setMessage(null);
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);

    try {
      const data = await defaultApi.login(trimmedEmail);
      const successMessage = (data as { message?: string }).message ?? 'Check your email for the login link.';
      setMessage(successMessage);
      window.dispatchEvent(new Event('auth-change'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to log in.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader
        label="Login"
        title="Sign in with your email"
        description="Enter the email you used to register. Approved accounts will receive a login link."
      />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={email}
            loading={isSubmitting}
            onChange={(value) => setEmail(value)}
            onFocusReset={resetFeedback}
            onSubmit={handleLogin}
            inputId="login-email"
            inputLabel="Email address"
            inputType="email"
            inputMode="email"
            autoComplete="email"
            placeholder="Enter your email address"
            submitIcon={<ArrowRight aria-hidden className="h-5 w-5" />}
            submitLabel="Send login link"
          />

          <div className="mt-6 space-y-3 min-h-[120px]">
            {error ? <AddCaseNotice tone="error" message={error} /> : null}

            {isSubmitting ? (
              <AddCaseNotice
                tone="loading"
                icon={<Loader2 aria-hidden className="h-5 w-5 animate-spin text-slate-600" />}
                message="Sending login link…"
              />
            ) : null}

            {!isSubmitting && message ? <AddCaseNotice tone="info" message={message} /> : null}
          </div>
        </div>
      </div>
    </>
  );
}
