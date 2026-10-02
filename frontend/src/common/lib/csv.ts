import { useEffect } from 'react';

/** Hands the browser a small text file to save, without a round trip to the server. */
export function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Runs `check` a moment after the text stops changing, so a paste or a chosen
 * file is previewed without a separate button. The caller drops any response
 * that does not answer the latest request.
 */
export function useAutoPreview(
  text: string,
  deps: unknown[],
  check: () => void,
  delay = 400,
) {
  useEffect(() => {
    if (!text.trim()) return;
    const timer = setTimeout(check, delay);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, ...deps]);
}
