import { PageHeader } from '@/components/custom/PageHeader';

export function LogoutPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="Logout"
        title="You have been logged out"
        description="Authentication is not wired yet. This page is a placeholder for the logout flow."
      />

      <div className="bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-5">
        <p className="text-slate-700 m-0">Use the navbar to navigate elsewhere.</p>
      </div>
    </div>
  );
}
