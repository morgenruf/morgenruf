import { useEffect, useRef } from 'react';
import { useRouterState } from '@tanstack/react-router';
import LoadingBar, { type LoadingBarRef } from 'react-top-loading-bar';

export function NavigationLoadingBar() {
  const { pending, navigationKey } = useRouterState({
    select: (state) => ({
      pending: state.status === 'pending' || state.isLoading,
      navigationKey: state.location.href,
    }),
  });
  const bar = useRef<LoadingBarRef>(null);
  const previous = useRef({ key: navigationKey, pending: false });

  useEffect(() => {
    if (pending) bar.current?.start();
    else if (previous.current.pending || previous.current.key !== navigationKey)
      bar.current?.complete();

    previous.current = { key: navigationKey, pending };
  }, [navigationKey, pending]);

  return (
    <LoadingBar
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
