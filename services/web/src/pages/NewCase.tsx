import { PageHeader } from '@/components/custom/PageHeader';

export function NewCasePage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="New Case"
        title="Create a New Case"
        description="This will host the case intake form. For now it is just a placeholder screen."
      />

      <div className="bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-5">
        <p className="text-slate-700 m-0">
          Form coming soon. Use the navbar to switch back to overview.
        </p>
      </div>
    </div>
  );
}
