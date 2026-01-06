import { PageHeader } from '@/components/custom/PageHeader';

export function ErrorMagicLinkPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="Magic link"
        title="This link did not work"
        description="Oops, that didn't work. This magic link is expired."
      />
    </div>
  );
}
