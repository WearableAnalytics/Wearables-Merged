import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { AuthEmailFormPage } from '@/components/custom/AuthEmailFormPage';
import { getTrimmedOrNull } from '@/lib/input';
import { useMessageToast } from '@/lib/toast';

export function AccessPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useMessageToast('error', 'access-error', error);

  useEffect(() => {
    if (!authLoading && user) {
      navigate('/overview', { replace: true });
    }
  }, [authLoading, navigate, user]);

  const resetFeedback = () => {
    setError(null);
  };

  const handleAccess = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = getTrimmedOrNull(email);

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
    <AuthEmailFormPage
      headerLabel="Access"
      headerTitle="Sign in or request access"
      headerDescription="Enter your email to sign in or request access."
      email={email}
      loading={loading}
      onEmailChange={setEmail}
      onFocusReset={resetFeedback}
      onSubmit={handleAccess}
      inputId="access-email"
      submitLabel="Continue"
    />
  );
}
