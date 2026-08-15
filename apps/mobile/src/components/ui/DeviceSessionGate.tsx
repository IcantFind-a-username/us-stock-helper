import type { PropsWithChildren } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PairDeviceScreen } from "@/screens/PairDeviceScreen";
import { useDeviceSession } from "@/state/DeviceSessionProvider";
import { colors, layout, radius, shadow, spacing } from "@/theme/tokens";

/**
 * Stands between an unpaired device and the rest of the app.
 *
 * Letting the screens mount without a token would leave every one of them
 * showing an empty or failed state whose real cause — no pairing — is nowhere
 * on the page. The gate makes that cause the whole screen instead.
 */
export function DeviceSessionGate({ children }: PropsWithChildren) {
  const { pairingRequired, session, forgetDevice } = useDeviceSession();
  // This gate sits above the tab navigator (and above every non-tab screen
  // reached from it), so a fixed bottom offset either overlaps the tab bar's
  // own band on tabbed screens or floats over content that has no tab bar at
  // all. Clearing `layout.tabBarHeight` plus the device's own bottom inset —
  // on every screen, tabbed or not — is what keeps a mis-tap here from ever
  // landing on 复盘 or Agent's corner instead of the tab underneath it.
  const insets = useSafeAreaInsets();
  const recoverBottom = insets.bottom + layout.tabBarHeight + spacing.sm;

  if (!pairingRequired) return <>{children}</>;
  if (session.status !== "paired") return <PairDeviceScreen />;
  return (
    <View style={styles.root}>
      {children}
      {/*
       * The server can revoke a device at any point in the session, and
       * nothing downstream of this gate notices that on its own — every
       * screen would just keep answering auth-required forever. reportRevoked
       * and forgetDevice exist for exactly this, but neither has a caller in
       * production: this is that caller, kept reachable from every screen
       * instead of buried behind a state transition nothing ever triggers.
       * It does not resurrect the old credential — it clears the local one
       * and sends the device back through PairDeviceScreen, where a fresh
       * code from the operator is required, so a device the server actually
       * revoked stays revoked server-side.
       */}
      <Pressable
        accessibilityLabel="重新配对设备"
        accessibilityRole="button"
        onPress={() => void forgetDevice()}
        style={({ pressed }) => [
          styles.recover,
          { bottom: recoverBottom },
          pressed && styles.recoverPressed,
        ]}>
        <Text style={styles.recoverText}>配对失效？重新配对</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  recover: {
    alignItems: "center",
    backgroundColor: colors.card,
    borderColor: colors.line,
    borderRadius: radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: "center",
    // The platform's own minimum tappable size, not the smaller pill this
    // used to ship at — a short target here is a second way to mis-tap it.
    minHeight: 44,
    paddingHorizontal: spacing.md,
    position: "absolute",
    right: spacing.md,
    // Painted after the navigator regardless, so an explicit zIndex keeps its
    // stacking order a property of this component instead of an accident of
    // where it happens to sit in the tree.
    zIndex: 10,
    ...shadow.card,
  },
  recoverPressed: { opacity: 0.66 },
  recoverText: { color: colors.blue, fontSize: 11, fontWeight: "800" },
});
