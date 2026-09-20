import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { ScrollArea } from '@base-ui/react/scroll-area';

export function AppMain({
  children,
  pathname,
}: {
  children: ReactNode;
  pathname?: string;
}) {
  const viewport = useRef<HTMLDivElement>(null);

  // Keep filter and dialog navigation in place, but start a new page at the top.
  useLayoutEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
  }, [pathname]);

  return (
    <ScrollArea.Root
      data-slot="main-scroll-area"
      className="relative isolate min-h-0 min-w-0 flex-1 overflow-hidden"
    >
      <ScrollArea.Viewport
        ref={viewport}
        render={<main />}
        role="main"
        id="main"
        className="h-full w-full overscroll-contain focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
        style={{ overflowX: 'hidden' }}
      >
        <ScrollArea.Content className="min-h-full" style={{ minWidth: 0 }}>
          {children}
        </ScrollArea.Content>
      </ScrollArea.Viewport>
      <ScrollArea.Scrollbar
        data-slot="main-scrollbar"
        orientation="vertical"
        className="pointer-events-none z-20 m-px flex w-2 justify-center p-0.5 opacity-0 transition-opacity duration-150 data-hovering:pointer-events-auto data-hovering:opacity-100 data-scrolling:pointer-events-auto data-scrolling:opacity-100 data-scrolling:duration-0"
      >
        <ScrollArea.Thumb className="w-full rounded-full bg-foreground/30 hover:bg-foreground/50" />
      </ScrollArea.Scrollbar>
    </ScrollArea.Root>
  );
}
