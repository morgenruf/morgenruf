'use client';

import * as React from 'react';
import { ScrollArea as ScrollAreaPrimitive } from '@base-ui/react/scroll-area';

import { cn } from '@/common/lib/utils';

type Orientation = 'vertical' | 'horizontal' | 'both';

function ScrollAreaRoot({
  className,
  ...props
}: ScrollAreaPrimitive.Root.Props) {
  return (
    <ScrollAreaPrimitive.Root
      data-slot="scroll-area"
      className={cn(
        'relative flex min-h-0 min-w-0 flex-col overflow-hidden',
        className,
      )}
      {...props}
    />
  );
}

function ScrollAreaViewport({
  className,
  orientation = 'vertical',
  style,
  ...props
}: ScrollAreaPrimitive.Viewport.Props & { orientation?: Orientation }) {
  return (
    <ScrollAreaPrimitive.Viewport
      data-slot="scroll-area-viewport"
      className={cn(
        'min-h-0 min-w-0 w-full flex-1 rounded-[inherit] focus-visible:-outline-offset-2 data-has-overflow-x:overscroll-x-contain data-has-overflow-y:overscroll-y-contain',
        className,
      )}
      style={{
        ...(orientation === 'vertical' && { overflowX: 'hidden' }),
        ...(orientation === 'horizontal' && { overflowY: 'hidden' }),
        ...style,
      }}
      {...props}
    />
  );
}

function ScrollAreaContent({
  style,
  ...props
}: ScrollAreaPrimitive.Content.Props) {
  return (
    <ScrollAreaPrimitive.Content
      data-slot="scroll-area-content"
      style={{ minWidth: 0, ...style }}
      {...props}
    />
  );
}

function ScrollBar({
  className,
  orientation = 'vertical',
  ...props
}: ScrollAreaPrimitive.Scrollbar.Props) {
  return (
    <ScrollAreaPrimitive.Scrollbar
      data-slot="scroll-area-scrollbar"
      orientation={orientation}
      className={cn(
        'pointer-events-none z-20 m-px flex touch-none select-none p-0.5 opacity-0 transition-opacity duration-150 data-hovering:pointer-events-auto data-hovering:opacity-100 data-scrolling:pointer-events-auto data-scrolling:opacity-100 data-scrolling:duration-0',
        orientation === 'vertical'
          ? 'w-2 justify-center'
          : 'h-2 flex-col justify-center',
        className,
      )}
      {...props}
    >
      <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-foreground/30 hover:bg-foreground/50" />
    </ScrollAreaPrimitive.Scrollbar>
  );
}

function ScrollArea({
  children,
  orientation = 'vertical',
  viewportProps,
  contentClassName,
  ...props
}: ScrollAreaPrimitive.Root.Props & {
  orientation?: Orientation;
  viewportProps?: React.ComponentProps<typeof ScrollAreaViewport>;
  contentClassName?: string;
}) {
  return (
    <ScrollAreaRoot {...props}>
      <ScrollAreaViewport orientation={orientation} {...viewportProps}>
        <ScrollAreaContent className={contentClassName}>
          {children}
        </ScrollAreaContent>
      </ScrollAreaViewport>
      {orientation !== 'horizontal' && <ScrollBar />}
      {orientation !== 'vertical' && <ScrollBar orientation="horizontal" />}
      {orientation === 'both' && <ScrollAreaPrimitive.Corner />}
    </ScrollAreaRoot>
  );
}

export {
  ScrollArea,
  ScrollAreaRoot,
  ScrollAreaViewport,
  ScrollAreaContent,
  ScrollBar,
};
