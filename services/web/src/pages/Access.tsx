import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export function AccessPage() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'access-error' });
    } else {
      toast.dismiss('access-error');
    }
  }, [error]);


  const resetFeedback = () => {
    setError(null);
  };

  const handleAccess = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setLoading(true);
    setError(null);

    const sendToRequestSent = (payload: {
      title: string;
      description: string;
      message: string;
    }) => {
      navigate('/request-sent', {
        replace: true,
        state: payload,
      });
    };

    const handleDirectAuth = async (data: unknown): Promise<boolean> => {
      if (!isDirectAuthResponse(data)) {
        return false;
      }
      await refreshUser();
      navigate('/overview', { replace: true });
      return true;
    };

    try {
      const data = await defaultApi.login(trimmedEmail);
      if (await handleDirectAuth(data)) {
        setLoading(false);
        return;
      }
      const successMessage =
        (data as { message?: string }).message ?? 'Check your email for the login link.';
      sendToRequestSent({
        title: 'Check your email',
        description: 'If your account is approved, we will send a secure login link.',
        message: successMessage,
      });
      setLoading(false);
      return;
    } catch (err) {
      const error = err as Error & { status?: number; redirectToSignup?: boolean; code?: string };
      if (error.code === 'PENDING_APPROVAL') {
        sendToRequestSent({
          title: 'Request pending',
          description: 'Your account is awaiting approval. We will email you once it is ready.',
          message: error.message || 'Your account is awaiting approval.',
        });
        setLoading(false);
        return;
      }

      if (error.status !== 404 || !error.redirectToSignup) {
        setError(error.message || 'Unable to process request.');
        setLoading(false);
        return;
      }
    }

    try {
      const data = await defaultApi.register(trimmedEmail);
      if (await handleDirectAuth(data)) {
        return;
      }
      const successMessage =
        (data as { message?: string }).message ?? 'Your account is awaiting admin approval.';
      sendToRequestSent({
        title: 'Request submitted',
        description: 'We will review your request and email you with next steps.',
        message: successMessage,
      });
    } catch (err) {
      const error = err as Error & { status?: number };
      if (error.status === 409) {
        try {
          const data = await defaultApi.login(trimmedEmail);
          if (await handleDirectAuth(data)) {
            return;
          }
          const successMessage =
            (data as { message?: string }).message ?? 'Check your email for the login link.';
          sendToRequestSent({
            title: 'Check your email',
            description: 'If your account is approved, we will send a secure login link.',
            message: successMessage,
          });
          return;
        } catch (loginErr) {
          const fallback = loginErr as Error;
          setError(fallback.message || 'Unable to process request.');
        }
      } else {
        setError(error.message || 'Unable to process request.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        label="Access"
        title="Sign in or request access"
        description="Enter your email to sign in or request access."
      />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={email}
            loading={loading}
            onChange={(value) => setEmail(value)}
            onFocusReset={resetFeedback}
            onSubmit={handleAccess}
            inputId="access-email"
            inputLabel="Email address"
            inputType="email"
            inputMode="email"
            autoComplete="email"
            placeholder="Enter your email address"
            submitIcon={<ArrowRight aria-hidden className="h-5 w-5" />}
            submitLabel="Continue"
          />
        </div>
      </div>
    </>
  );
}
