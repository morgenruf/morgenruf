import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Recharts measures tick labels in a hidden off-screen span that keeps the
// last measured text, so text queries would match it next to the real tick.
configure({ defaultIgnore: 'script, style, #recharts_measurement_span' });

// TanStack Router manages scroll restoration; jsdom does not implement it.
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
}

afterEach(cleanup);
