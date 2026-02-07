import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { defaultApi } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export function LoginPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
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
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const data = await defaultApi.login(trimmedEmail);
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
        </div>
      </div>
    </>
  );
}
