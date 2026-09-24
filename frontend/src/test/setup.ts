import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// TanStack Router manages scroll restoration; jsdom does not implement it.
if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true });
}

afterEach(cleanup);
