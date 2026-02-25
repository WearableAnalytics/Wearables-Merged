import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

export type MonitoringViewOption<ViewId extends string = string> = {
  id: ViewId;
  label: string;
  kind: 'grafana' | 'custom';
};

export type QuickRangeOption = {
  label: string;
  durationMs: number;
};

type CaseMonitoringPanelProps<ViewId extends string = string> = {
  loading: boolean;
  error: string | null;
  monitoringViews: MonitoringViewOption<ViewId>[];
  separatedMonitoringViewIds?: ViewId[];
  activeMonitoringView: ViewId;
  onMonitoringViewChange: (viewId: ViewId) => void;
  activeMonitoringConfig: MonitoringViewOption<ViewId>;
  activeQuickRangeOptions: QuickRangeOption[];
  onQuickRangeSelect: (durationMs: number) => void;
  fromInput: string;
  toInput: string;
  maxToInput: string;
  onFromInputChange: (value: string) => void;
  onToInputChange: (value: string) => void;
  timeRangeError: string | null;
  activeGrafanaUrl: string | null;
};

export function CaseMonitoringPanel<ViewId extends string = string>({
  loading,
  error,
  monitoringViews,
  separatedMonitoringViewIds = [],
  activeMonitoringView,
  onMonitoringViewChange,
  activeMonitoringConfig,
  activeQuickRangeOptions,
  onQuickRangeSelect,
  fromInput,
  toInput,
  maxToInput,
  onFromInputChange,
  onToInputChange,
  timeRangeError,
  activeGrafanaUrl,
}: CaseMonitoringPanelProps<ViewId>) {
  const separatedViewIdSet = new Set(separatedMonitoringViewIds);
  const groupedMonitoringViews = monitoringViews.filter((view) => !separatedViewIdSet.has(view.id));
  const separatedMonitoringViews = monitoringViews.filter((view) => separatedViewIdSet.has(view.id));

  const renderMonitoringButton = (view: MonitoringViewOption<ViewId>, separated = false) => {
    const isActive = activeMonitoringView === view.id;
    return (
      <Button
        key={view.id}
        type="button"
        size={separated ? 'tabGroup' : 'sm'}
        variant={separated ? 'aiTab' : isActive ? 'default' : 'ghost'}
        className="px-3"
        aria-pressed={isActive}
        onClick={() => onMonitoringViewChange(view.id)}
      >
        {view.label}
      </Button>
    );
  };

  return (
    <div className="surface-card p-4 md:col-span-3">
      {error ? (
        <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
          {error}
        </div>
      ) : loading ? (
        <div className="surface-subtle flex items-center gap-2 px-3 py-2 text-sm font-semibold text-muted-foreground">
          <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
          Loading grafana dashboard…
        </div>
      ) : (
        activeMonitoringConfig.kind === 'grafana' ? (
          <div className="relative w-full space-y-3">
            <div className="flex max-w-full flex-wrap items-stretch gap-2">
              <div className="inline-flex max-w-full flex-wrap gap-2 rounded-xl border border-border bg-muted/40 p-1">
                {groupedMonitoringViews.map((view) => renderMonitoringButton(view))}
              </div>
              {separatedMonitoringViews.map((view) => renderMonitoringButton(view, true))}
            </div>
            <div className="surface-subtle px-3 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Data time range
              </p>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3 md:items-end">
                <div className="min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Quick range
                  </span>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {activeQuickRangeOptions.map((option) => (
                      <Button
                        key={option.label}
                        type="button"
                        size="sm"
                        variant="outline"
                        className="w-full px-2 font-normal"
                        onClick={() => onQuickRangeSelect(option.durationMs)}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>
                <label className="min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    From
                  </span>
                  <input
                    type="datetime-local"
                    className="field-input ui-control-h mt-2 w-full rounded-xl"
                    value={fromInput}
                    max={toInput}
                    onChange={(event) => onFromInputChange(event.target.value)}
                  />
                </label>
                <label className="min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Until
                  </span>
                  <input
                    type="datetime-local"
                    className="field-input ui-control-h mt-2 w-full rounded-xl"
                    value={toInput}
                    min={fromInput}
                    max={maxToInput}
                    onChange={(event) => onToInputChange(event.target.value)}
                  />
                </label>
              </div>
            </div>
            {timeRangeError ? (
              <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
                {timeRangeError}
              </div>
            ) : null}
            {activeGrafanaUrl ? (
              <iframe
                title={`Grafana ${activeMonitoringConfig.label} dashboard`}
                src={activeGrafanaUrl}
                // Cross-origin iframes cannot be auto-sized reliably from parent page.
                className="h-[600px] md:h-[800px] lg:h-[1000px] w-full rounded-xl"
                allow="fullscreen"
              />
            ) : (
              <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
                Missing configuration for the selected dashboard view.
              </div>
            )}
          </div>
        ) : (
          <div className="surface-subtle px-3 py-3 text-sm font-semibold text-foreground">
            Content for this monitoring view is not configured yet.
          </div>
        )
      )}
    </div>
  );
}
