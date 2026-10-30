import { Link } from 'react-router-dom';
import { PageHeader } from '@/components/custom/PageHeader';
import { PasswordChangeForm } from '@/components/account/PasswordChangeForm';

export function SetPasswordPage() {
  return (
    <div className="mx-auto w-full max-w-2xl">
      <PageHeader
        label="Account setup"
        title="Set your password"
        description="Your temporary password allows this setup step only. Choose your own password before you access the application."
      />
      <PasswordChangeForm initial />
      <Link to="/login" className="mt-4 inline-block text-primary underline">
        Return to sign-in
      </Link>
    </div>
  );
}
