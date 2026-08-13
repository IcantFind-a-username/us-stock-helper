import type { PropsWithChildren } from "react";

import { PairDeviceScreen } from "@/screens/PairDeviceScreen";
import { useDeviceSession } from "@/state/DeviceSessionProvider";

/**
 * Stands between an unpaired device and the rest of the app.
 *
 * Letting the screens mount without a token would leave every one of them
 * showing an empty or failed state whose real cause — no pairing — is nowhere
 * on the page. The gate makes that cause the whole screen instead.
 */
export function DeviceSessionGate({ children }: PropsWithChildren) {
  const { pairingRequired, session } = useDeviceSession();

  if (!pairingRequired || session.status === "paired") return <>{children}</>;
  return <PairDeviceScreen />;
}
