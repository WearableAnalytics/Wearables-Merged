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
            <div className="inline-flex max-w-full flex-wrap gap-2 rounded-xl border border-border bg-muted/40 p-1">
              {monitoringViews.map((view) => {
                const isActive = activeMonitoringView === view.id;
                return (
                  <Button
                    key={view.id}
                    type="button"
                    size="sm"
                    variant={isActive ? 'default' : 'ghost'}
                    className="px-3"
                    aria-pressed={isActive}
                    onClick={() => onMonitoringViewChange(view.id)}
                  >
                    {view.label}
                  </Button>
                );
              })}
            </div>
            <div className="surface-subtle px-3 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                Data time range
              </p>
              <div className="mt-3 flex flex-wrap items-end gap-3">
                <div className="min-w-[220px]">
                  <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    Quick range
                  </span>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {activeQuickRangeOptions.map((option) => (
                      <Button
                        key={option.label}
                        type="button"
                        size="sm"
                        variant="outline"
                        className="px-3 font-normal"
                        onClick={() => onQuickRangeSelect(option.durationMs)}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>
                <label className="min-w-[240px] flex-1">
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
                <label className="min-w-[240px] flex-1">
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
