import type { PropsWithChildren } from "react";

import { fixtureRepository } from "@/fixtures/repository";
import { useDeviceSession } from "@/state/DeviceSessionProvider";
import { MarketDataProvider } from "@/state/MarketDataProvider";

/**
 * Hands the paired device's token to the layer that spends it.
 *
 * This lives outside the route file so the join can be tested as the app
 * actually assembles it. A token that reached the Keychain but never reached a
 * request would leave the pairing screen saying "已配对" while every market
 * surface behind it answered nothing, and no test of either half alone would
 * catch it.
 *
 * It is mounted below the gate so the market layer is only ever built once a
 * token exists to build it with, and rebuilt if the pairing changes.
 */
export function PairedMarketData({ children }: PropsWithChildren) {
  const { deviceToken } = useDeviceSession();

  return (
    <MarketDataProvider
      deviceToken={deviceToken}
      demoWatchlist={fixtureRepository.getDashboard("short").watchlist}>
      {children}
    </MarketDataProvider>
  );
}
