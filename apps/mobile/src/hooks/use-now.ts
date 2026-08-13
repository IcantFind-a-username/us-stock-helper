import { useEffect, useState } from "react";

/**
 * A clock that keeps ticking while the screen stays open.
 *
 * "3 分钟前" is a claim about the moment it was rendered, and it silently
 * becomes false a minute later. Anything that shows elapsed time reads its
 * present from here instead of from render time.
 */
export function useNow(intervalMs = 15_000): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  return now;
}
