/** Keep legacy query strings as strings, including free text such as q=true. */
export function parseSearch(search: string): Record<string, string> {
  const values: Record<string, string> = {};

  for (const [key, value] of new URLSearchParams(search)) {
    if (!Object.hasOwn(values, key))
      Object.defineProperty(values, key, {
        value,
        enumerable: true,
        configurable: true,
        writable: true,
      });
  }

  return values;
}

export function stringifySearch(search: Record<string, unknown>): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(search)) {
    if (
      value !== undefined &&
      value !== null &&
      value !== '' &&
      value !== false
    )
      params.set(key, String(value));
  }

  const result = params.toString();

  return result ? `?${result}` : '';
}
