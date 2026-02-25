import type { ReactNode } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InfoItem } from '@/components/custom/InfoItem';

export type CaseDisplayItem = {
  key: string;
  label: string;
  value: ReactNode;
};

type CollapsibleInfoSectionProps = {
  title: string;
  isCollapsed: boolean;
  onToggle: () => void;
  items: CaseDisplayItem[];
  emptyMessage: string;
  itemKeyPrefix: string;
};

function CollapsibleInfoSection({
  title,
  isCollapsed,
  onToggle,
  items,
  emptyMessage,
  itemKeyPrefix,
}: CollapsibleInfoSectionProps) {
  return (
    <div>
      <button
        type="button"
        className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-left text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        aria-expanded={!isCollapsed}
        onClick={onToggle}
      >
        <ChevronRight aria-hidden className={`h-4 w-4 transition-transform ${isCollapsed ? '' : 'rotate-90'}`} />
        <span>{title}</span>
      </button>
      {isCollapsed ? null : items.length === 0 ? (
        <div className="surface-subtle mt-2 px-3 py-2 text-sm text-muted-foreground">{emptyMessage}</div>
      ) : (
        <dl className="mt-2 grid grid-cols-1 gap-3">
          {items.map((item) => {
            const valueTitle =
              typeof item.value === 'string' || typeof item.value === 'number' ? String(item.value) : undefined;

            return (
              <InfoItem
                key={`${itemKeyPrefix}-${item.key}`}
                label={item.label}
                value={
                  <span className="block truncate" title={valueTitle}>
                    {item.value}
                  </span>
                }
              />
            );
          })}
        </dl>
      )}
    </div>
  );
}

type CaseDataPanelProps = {
  loading: boolean;
  error: string | null;
  isDataPanelCollapsedMobile: boolean;
  onToggleDataPanelMobile: () => void;
  isPatientSectionCollapsed: boolean;
  onTogglePatientSection: () => void;
  isCaseSectionCollapsed: boolean;
  onToggleCaseSection: () => void;
  patientDisplayItems: CaseDisplayItem[];
  caseDisplayItems: CaseDisplayItem[];
};

export function CaseDataPanel({
  loading,
  error,
  isDataPanelCollapsedMobile,
  onToggleDataPanelMobile,
  isPatientSectionCollapsed,
  onTogglePatientSection,
  isCaseSectionCollapsed,
  onToggleCaseSection,
  patientDisplayItems,
  caseDisplayItems,
}: CaseDataPanelProps) {
  return (
    <aside className="surface-card p-4 md:col-span-1">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-section-title">Case Data</h2>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="md:hidden"
          aria-expanded={!isDataPanelCollapsedMobile}
          onClick={onToggleDataPanelMobile}
        >
          {isDataPanelCollapsedMobile ? 'Expand' : 'Collapse'}
          {isDataPanelCollapsedMobile ? (
            <ChevronDown aria-hidden className="h-4 w-4" />
          ) : (
            <ChevronUp aria-hidden className="h-4 w-4" />
          )}
        </Button>
      </div>

      <div className={`${isDataPanelCollapsedMobile ? 'hidden md:block' : 'block'} mt-3 space-y-4`}>
        {error ? (
          <div className="rounded-lg border border-[hsl(var(--warning)/0.35)] bg-[hsl(var(--warning)/0.16)] px-3 py-2 text-sm font-semibold text-foreground">
            {error}
          </div>
        ) : loading ? (
          <div className="surface-subtle flex items-center gap-2 px-3 py-2 text-sm font-semibold text-muted-foreground">
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            Loading case…
          </div>
        ) : (
          <>
            <CollapsibleInfoSection
              title="Patient"
              isCollapsed={isPatientSectionCollapsed}
              onToggle={onTogglePatientSection}
              items={patientDisplayItems}
              emptyMessage="No patient fields available."
              itemKeyPrefix="patient"
            />

            <CollapsibleInfoSection
              title="Case"
              isCollapsed={isCaseSectionCollapsed}
              onToggle={onToggleCaseSection}
              items={caseDisplayItems}
              emptyMessage="No case fields available."
              itemKeyPrefix="case"
            />
          </>
        )}
      </div>
    </aside>
  );
}
