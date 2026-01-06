import { PageHeader } from '@/components/custom/PageHeader';
import { SignedInAs } from '@/components/custom/SignedInAs';

const grafanaIframeSrc = import.meta.env.VITE_GRAFANA_IFRAME_URL ?? '/grafana/';

export function GrafanaPage() {
  return (
    <>
      <PageHeader
        label="Observability"
        title="Grafana"
        description="Secure Grafana embed served through the local proxy."
      />
      <SignedInAs />

      <section className="rounded-2xl border border-slate-200 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
        <div className="border-b border-slate-200 px-4 py-3 text-sm text-slate-500">
          <span className="font-mono">{grafanaIframeSrc}</span>
        </div>
        <div className="relative w-full">
          <iframe
            title="Grafana dashboard"
            src={grafanaIframeSrc}
            className="w-full h-[min(75vh,900px)] rounded-b-2xl"
            allow="fullscreen"
          />
        </div>
      </section>
    </>
  );
}
