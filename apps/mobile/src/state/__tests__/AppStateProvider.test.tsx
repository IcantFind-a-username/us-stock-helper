import { beforeEach, expect, it, jest } from "@jest/globals";
import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Button, Text } from "react-native";

import type { Horizon, JournalEntry } from "@/domain/models";
import { tradePlanFixtures } from "@/fixtures/advisers";

import { AppStateProvider, useAppState } from "../AppStateProvider";
import { storage, type StorageAdapter } from "../persistence";

jest.mock("../persistence", () => ({
  storage: {
    get: jest.fn(),
    set: jest.fn(),
  },
}));

const mockedStorage = storage as jest.Mocked<StorageAdapter>;
const selectedPlan = tradePlanFixtures[0]!;
const journalEntry: JournalEntry = {
  id: "journal-1",
  symbol: "NVDA",
  side: "long",
  quantity: 10,
  executionPrice: 141.2,
  executedAt: "2026-07-24T08:00:00Z",
  executionDelaySeconds: 30,
  pnl: 0,
  pnlState: "unrealized",
  decision: "followed",
  slippage: 0.01,
  notes: "按计划执行",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });

  return { promise, resolve };
}

beforeEach(() => {
  mockedStorage.get.mockReset();
  mockedStorage.set.mockReset();
  mockedStorage.get.mockResolvedValue(null);
  mockedStorage.set.mockResolvedValue(undefined);
});

function Probe() {
  const { addJournalEntry, horizon, journalEntries, savePlan, savedPlans, setHorizon } = useAppState();

  return (
    <>
      <Text>{horizon}</Text>
      <Text>{`plans:${savedPlans.length}`}</Text>
      <Text>{`objective:${savedPlans[0]?.objectiveScore ?? "none"}`}</Text>
      <Text>{`journal:${journalEntries.length}`}</Text>
      <Button title="swing" onPress={() => setHorizon("swing")} />
      <Button title="save plan" onPress={() => savePlan(selectedPlan)} />
      <Button title="add entry" onPress={() => addJournalEntry(journalEntry)} />
    </>
  );
}

it("defaults to short and switches horizons", async () => {
  const view = await render(
    <AppStateProvider>
      <Probe />
    </AppStateProvider>,
  );

  expect(view.getByText("short")).toBeTruthy();
  await fireEvent.press(view.getByText("swing"));
  expect(view.getAllByText("swing")).not.toHaveLength(0);
});

it("waits for persisted state before rendering consumers", async () => {
  const storedHorizon = deferred<Horizon | null>();
  const storedPlans = deferred<typeof selectedPlan[] | null>();
  const storedEntries = deferred<JournalEntry[] | null>();
  mockedStorage.get
    .mockImplementationOnce(() => storedHorizon.promise as Promise<never>)
    .mockImplementationOnce(() => storedPlans.promise as Promise<never>)
    .mockImplementationOnce(() => storedEntries.promise as Promise<never>);

  const view = await render(
    <AppStateProvider>
      <Probe />
    </AppStateProvider>,
  );

  expect(view.queryByText("short")).toBeNull();

  storedHorizon.resolve("swing");
  storedPlans.resolve([selectedPlan]);
  storedEntries.resolve([journalEntry]);

  await waitFor(() => {
    expect(view.getAllByText("swing")).not.toHaveLength(0);
    expect(view.getByText("plans:1")).toBeTruthy();
    expect(view.getByText("journal:1")).toBeTruthy();
  });
});

it("persists a fixture plan and journal entry without changing its objective score", async () => {
  const view = await render(
    <AppStateProvider>
      <Probe />
    </AppStateProvider>,
  );

  await view.findByText("short");
  await fireEvent.press(view.getByText("save plan"));
  await fireEvent.press(view.getByText("add entry"));

  await waitFor(() => {
    expect(view.getByText("plans:1")).toBeTruthy();
    expect(view.getByText("objective:72")).toBeTruthy();
    expect(view.getByText("journal:1")).toBeTruthy();
  });
  expect(selectedPlan.objectiveScore).toBe(72);
  await waitFor(() => {
    expect(mockedStorage.set).toHaveBeenCalledWith("us-stock-helper/saved-plans", [selectedPlan]);
    expect(mockedStorage.set).toHaveBeenCalledWith("us-stock-helper/journal-entries", [journalEntry]);
  });
});
