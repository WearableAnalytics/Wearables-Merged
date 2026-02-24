import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { StatusCallout } from '@/components/custom/StatusCallout';
import { useAuth } from '@/context/AuthContext';
import { AuthEmailFormPage } from '@/components/custom/AuthEmailFormPage';
import { getTrimmedOrNull } from '@/lib/input';
import { getDefaultAuthenticatedPath } from '@/lib/userAccess';
import { useLoadingToast, useMessageToast } from '@/lib/toast';

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signupInfoMessage, setSignupInfoMessage] = useState<string | null>(null);
  useMessageToast('error', 'login-error', error);
  useLoadingToast('login-loading', isSubmitting, 'Signing you in…');

  const resetFeedback = () => {
    setError(null);
    setSignupInfoMessage(null);
  };

  useEffect(() => {
    if (!authLoading && user) {
      navigate(getDefaultAuthenticatedPath(user), { replace: true });
    }
  }, [user, authLoading, navigate]);

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = getTrimmedOrNull(email);

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setSignupInfoMessage(null);

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
          tone: 'success',
        },
      });
    } catch (err) {
      if (
        err instanceof Error &&
        (err as Error & { redirectToSignup?: boolean }).redirectToSignup
      ) {
        setSignupInfoMessage(err.message || 'This email is not registered. Please sign up first.');
      } else {
        setError(err instanceof Error ? err.message : 'Unable to log in.');
      }
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
      footer={
        <div className="w-full space-y-3">
          <p className="m-0 w-full text-center text-sm text-muted-foreground">
            Need access?{' '}
            <Link to="/register" className="font-semibold text-foreground underline-offset-2 hover:underline">
              Register here
            </Link>
            .
          </p>
          {signupInfoMessage ? <StatusCallout tone="error" message={signupInfoMessage} /> : null}
        </div>
      }
    />
  );
}
