import type { ReactNode } from 'react';
import {
  AnimatePresence,
  motion,
  useIsPresent,
  useReducedMotion,
} from 'motion/react';

import { cn } from '@/common/lib/utils';

type LoadingTransitionProps = {
  pending: boolean;
  children: ReactNode;
  className?: string;
};

function LoadingTransitionContent({
  children,
  className,
}: LoadingTransitionProps) {
  const reducedMotion = useReducedMotion();
  const present = useIsPresent();

  return (
    <motion.div
      className={cn('col-start-1 row-start-1 min-w-0 space-y-6', className)}
      inert={!present}
      aria-hidden={!present || undefined}
      initial={reducedMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{
        opacity: reducedMotion ? 1 : 0,
        transition: { duration: reducedMotion ? 0 : 0.12, ease: 'easeIn' },
      }}
      transition={{ duration: reducedMotion ? 0 : 0.18, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  );
}

/** Crossfade the skeleton and ready content in the same layout slot. */
export function LoadingTransition(props: LoadingTransitionProps) {
  return (
    <div className="grid min-w-0">
      <AnimatePresence initial={false} mode="sync">
        <LoadingTransitionContent
          key={props.pending ? 'loading' : 'ready'}
          {...props}
        />
      </AnimatePresence>
    </div>
  );
}
