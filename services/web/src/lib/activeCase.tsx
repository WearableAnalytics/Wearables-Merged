import type { ReactNode } from 'react';
import { createContext, useContext, useMemo, useState, useCallback } from 'react';
import type { Case, Patient } from '@/api/openapi-client';

type ActiveCaseContextValue = {
  activeCase: Case | null;
  patient: Patient | null;
  setActiveCase: (value: { caseData: Case; patient: Patient }) => void;
  clearActiveCase: () => void;
};

const ActiveCaseContext = createContext<ActiveCaseContextValue | undefined>(undefined);

export function ActiveCaseProvider({ children }: { children: ReactNode }) {
  const [activeCase, setActiveCaseState] = useState<Case | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);

  const setActiveCase = useCallback(({ caseData, patient }: { caseData: Case; patient: Patient }) => {
    setActiveCaseState(caseData);
    setPatient(patient);
  }, []);

  const clearActiveCase = useCallback(() => {
    setActiveCaseState(null);
    setPatient(null);
  }, []);

  const value = useMemo(
    () => ({
      activeCase,
      patient,
      setActiveCase,
      clearActiveCase,
    }),
    [activeCase, patient, setActiveCase, clearActiveCase],
  );

  return <ActiveCaseContext.Provider value={value}>{children}</ActiveCaseContext.Provider>;
}

export function useActiveCase() {
  const context = useContext(ActiveCaseContext);
  if (!context) {
    throw new Error('useActiveCase must be used within an ActiveCaseProvider');
  }

  return context;
}
