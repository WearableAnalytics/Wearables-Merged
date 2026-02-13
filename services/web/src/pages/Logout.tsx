import { PageHeader } from '@/components/custom/PageHeader';
import { SignedInAs } from '@/components/custom/SignedInAs';

export function LogoutPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="Logout"
        title="You have been logged out"
        description="Your session has ended. Use the navbar to sign back in."
      />
      <SignedInAs />

      <div className="surface-card p-5">
        <p className="m-0 text-muted-foreground">Use the navbar to navigate elsewhere.</p>
      </div>
    </div>
  );
}
