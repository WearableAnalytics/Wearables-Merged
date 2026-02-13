import { Link, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import wLogo from '@/assets/W.png';
import { useAuth } from '@/context/AuthContext';

export function LandingPage() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) {
      navigate('/overview', { replace: true });
    }
  }, [user, loading, navigate]);

  return (
    <section className="relative flex min-h-[70vh] items-center justify-center">
      <div
        className="absolute inset-0 -z-10 opacity-70"
        aria-hidden="true"
        style={{
          backgroundImage:
            'radial-gradient(circle at 20% 20%, var(--surface-gradient-primary), transparent 35%), radial-gradient(circle at 80% 0%, var(--surface-gradient-secondary), transparent 32%)',
        }}
      />

      <div className="surface-glass w-full max-w-3xl overflow-hidden">
        <div className="relative px-8 py-12 text-center md:px-12 md:py-16">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-card/90 shadow-sm">
            <img src={wLogo} alt="W Logo" className="h-10 w-10 object-contain" />
          </div>

          <div className="mb-2 text-page-label tracking-[0.14em]">
            Wearables Platform
          </div>

          <h1 className="text-hero-title">
            Welcome back. Choose how you want to continue.
          </h1>
          <p className="mt-3 text-base text-muted-foreground">
            Access patient cases and monitor progress by signing in, or create a new account to get started.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
            <Button asChild size="lg" className="w-full sm:w-auto px-7">
              <Link to="/access">Access</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
