import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { AuthEmailFormPage } from '@/components/custom/AuthEmailFormPage';
import { getTrimmedOrNull } from '@/lib/input';

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetFeedback = () => {
    setError(null);
  };

  useEffect(() => {
    if (!authLoading && user) {
      navigate('/overview', { replace: true });
    }
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'login-error' });
    } else {
      toast.dismiss('login-error');
    }
  }, [error]);

  useEffect(() => {
    if (isSubmitting) {
      toast.loading('Sending login link…', { id: 'login-loading' });
    } else {
      toast.dismiss('login-loading');
    }
  }, [isSubmitting]);

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = getTrimmedOrNull(email);

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const data = await defaultApi.login(trimmedEmail);
      if (isDirectAuthResponse(data)) {
        await refreshUser();
        navigate('/overview', { replace: true });
        return;
      }
      const successMessage = (data as { message?: string }).message ?? 'Check your email for the login link.';
      navigate('/request-sent', {
        replace: true,
        state: {
          title: 'Check your email',
          description: 'If your account is approved, we will send a secure login link.',
          message: successMessage,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to log in.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthEmailFormPage
      headerLabel="Login"
      headerTitle="Sign in with your email"
      headerDescription="Enter the email you used to register. Approved accounts will receive a login link."
      email={email}
      loading={isSubmitting}
      onEmailChange={setEmail}
      onFocusReset={resetFeedback}
      onSubmit={handleLogin}
      inputId="login-email"
      submitLabel="Send login link"
    />
  );
}
