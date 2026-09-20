import { vi } from 'vitest';

export function mockViewport(initialWidth = 1024) {
  let width = initialWidth;
  const queries = new Set<MediaQueryList>();
  const matches = (query: string) => {
    const max = query.match(/max-width:\s*(\d+)px/);
    const min = query.match(/min-width:\s*(\d+)px/);
    return (
      !!(max || min) &&
      (!max || width <= Number(max[1])) &&
      (!min || width >= Number(min[1]))
    );
  };

  vi.stubGlobal('innerWidth', width);
  vi.stubGlobal(
    'matchMedia',
    vi.fn((media: string) => {
      const target = new EventTarget();
      const query = Object.assign(target, {
        media,
        get matches() {
          return matches(media);
        },
        onchange: null,
        addListener: (listener: EventListener) =>
          target.addEventListener('change', listener),
        removeListener: (listener: EventListener) =>
          target.removeEventListener('change', listener),
      }) as MediaQueryList;
      Object.defineProperty(query, 'matches', { get: () => matches(media) });
      queries.add(query);
      return query;
    }),
  );

  return (nextWidth: number) => {
    const previous = new Map(
      [...queries].map((query) => [query, query.matches]),
    );
    width = nextWidth;
    vi.stubGlobal('innerWidth', width);
    for (const query of queries) {
      if (query.matches !== previous.get(query)) {
        query.dispatchEvent(
          Object.assign(new Event('change'), {
            matches: query.matches,
            media: query.media,
          }),
        );
      }
    }
    window.dispatchEvent(new Event('resize'));
  };
}
