import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";

import type { Horizon, JournalEntry, TradePlan } from "@/domain/models";
import { storage } from "./persistence";

const persistedKeys = {
  savedPlans: "us-stock-helper/saved-plans",
  journalEntries: "us-stock-helper/journal-entries",
  horizon: "us-stock-helper/horizon",
} as const;

interface AppStateValue {
  horizon: Horizon;
  setHorizon(value: Horizon): void;
  savedPlans: TradePlan[];
  savePlan(plan: TradePlan): void;
  journalEntries: JournalEntry[];
  addJournalEntry(entry: JournalEntry): void;
}

const AppStateContext = createContext<AppStateValue | null>(null);

export function AppStateProvider({ children }: PropsWithChildren) {
  const [horizon, setHorizonState] = useState<Horizon>("short");
  const [savedPlans, setSavedPlans] = useState<TradePlan[]>([]);
  const [journalEntries, setJournalEntries] = useState<JournalEntry[]>([]);

  useEffect(() => {
    void Promise.all([
      storage.get<Horizon>(persistedKeys.horizon),
      storage.get<TradePlan[]>(persistedKeys.savedPlans),
      storage.get<JournalEntry[]>(persistedKeys.journalEntries),
    ]).then(([storedHorizon, storedPlans, storedEntries]) => {
      if (storedHorizon !== null) setHorizonState(storedHorizon);
      if (storedPlans !== null) setSavedPlans(storedPlans);
      if (storedEntries !== null) setJournalEntries(storedEntries);
    });
  }, []);

  const value = useMemo<AppStateValue>(
    () => ({
      horizon,
      setHorizon(nextHorizon) {
        setHorizonState(nextHorizon);
        void storage.set(persistedKeys.horizon, nextHorizon);
      },
      savedPlans,
      savePlan(plan) {
        setSavedPlans((currentPlans) => {
          const nextPlans = [...currentPlans.filter(({ id }) => id !== plan.id), plan];
          void storage.set(persistedKeys.savedPlans, nextPlans);
          return nextPlans;
        });
      },
      journalEntries,
      addJournalEntry(entry) {
        setJournalEntries((currentEntries) => {
          const nextEntries = [entry, ...currentEntries];
          void storage.set(persistedKeys.journalEntries, nextEntries);
          return nextEntries;
        });
      },
    }),
    [horizon, journalEntries, savedPlans],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const value = useContext(AppStateContext);
  if (value === null) throw new Error("useAppState must be used within AppStateProvider");
  return value;
}
