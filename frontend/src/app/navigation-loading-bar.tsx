import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { RouterProviderProps } from 'react-router';
import LoadingBar, { type LoadingBarRef } from 'react-top-loading-bar';

export function NavigationLoadingBar({
  router,
}: Pick<RouterProviderProps, 'router'>) {
  const { initialized, location, navigation } = useSyncExternalStore(
    router.subscribe,
    () => router.state,
  );
  const bar = useRef<LoadingBarRef>(null);
  const pending = !initialized || navigation.state !== 'idle';
  const navigationKey = navigation.location?.key ?? location.key;
  const previous = useRef({ key: navigationKey, pending: false });

  useEffect(() => {
    if (pending) {
      bar.current?.start();
    } else if (
      previous.current.pending ||
      previous.current.key !== navigationKey
    ) {
      bar.current?.complete();
    }

    previous.current = { key: navigationKey, pending };
  }, [navigationKey, pending]);

  return (
    <LoadingBar
      // A new navigation must not inherit the previous bar's fade timers.
      key={navigationKey}
      ref={bar}
      color="var(--primary)"
      height={3}
      shadow={false}
      loaderSpeed={300}
      waitingTime={300}
      transitionTime={200}
      containerClassName="navigation-loading-bar"
      containerStyle={{ pointerEvents: 'none', zIndex: 100 }}
    />
  );
}
