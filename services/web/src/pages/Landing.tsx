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
            'radial-gradient(circle at 20% 20%, rgba(14,165,233,0.22), transparent 35%), radial-gradient(circle at 80% 0%, rgba(59,130,246,0.18), transparent 32%)',
        }}
      />

      <div className="w-full max-w-3xl overflow-hidden rounded-3xl border border-white/70 bg-white/70 shadow-[0_25px_80px_rgba(15,23,42,0.12)] backdrop-blur-xl">
        <div className="relative px-8 py-12 text-center md:px-12 md:py-16">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-slate-200 bg-white/90 shadow-sm">
            <img src={wLogo} alt="W Logo" className="h-10 w-10 object-contain" />
          </div>

          <div className="mb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-sky-500">
            Wearables Platform
          </div>

          <h1 className="text-[clamp(28px,4vw,38px)] font-bold leading-tight text-slate-900">
            Welcome back. Choose how you want to continue.
          </h1>
          <p className="mt-3 text-base text-slate-600">
            Access patient cases and monitor progress by signing in, or create a new account to get started.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
            <Button asChild size="lg" className="w-full sm:w-auto px-7 py-5">
              <Link to="/access">Access</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
