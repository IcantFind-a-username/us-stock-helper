const { withPodfileProperties } = require("@expo/config-plugins");

/**
 * Keep local and generated iOS builds on one coherent native linkage mode.
 * The prebuilt React framework exposed a symbol-set mismatch with the pinned
 * Expo/RN native modules; building both RN and Expo modules from source avoids
 * mixing incompatible binaries.
 */
module.exports = function withBuildReactNativeFromSource(config) {
  return withPodfileProperties(config, (next) => {
    next.modResults["ios.buildReactNativeFromSource"] = "true";
    next.modResults.EXPO_USE_PRECOMPILED_MODULES = "false";
    return next;
  });
};
