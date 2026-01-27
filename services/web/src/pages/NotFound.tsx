import { PageHeader } from '@/components/custom/PageHeader';

export function NotFoundPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="Not found"
        title="Page not found"
        description="Use the navbar to navigate to an existing section."
      />
    </div>
  );
}
