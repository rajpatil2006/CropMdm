import { useEffect, useRef } from "react";

/**
 * Run `load` now and then every `intervalMs` while the component is mounted.
 * `load` receives an isActive() check so late responses can be ignored.
 * Changing anything in `deps` restarts the cycle.
 */
export default function usePolling(load, intervalMs, deps) {
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let active = true;
    const isActive = () => active;
    const run = () => loadRef.current(isActive);
    run();
    const timer = intervalMs ? setInterval(run, intervalMs) : null;
    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}
