import { useEffect, useState, type ReactNode } from 'react';

import { ThemeContext, type Theme } from './theme-context';

function initialTheme(): Theme {
  try {
    const value = localStorage.getItem('morgenruf-theme');

    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system');

  useEffect(() => {
    setThemeState(initialTheme());
  }, []);

  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)');
    const update = () =>
      document.documentElement.classList.toggle(
        'dark',
        theme === 'dark' || (theme === 'system' && media.matches),
      );

    update();
    media.addEventListener('change', update);

    return () => media.removeEventListener('change', update);
  }, [theme]);

  function setTheme(next: Theme) {
    setThemeState(next);

    try {
      localStorage.setItem('morgenruf-theme', next);
    } catch {
      /* Appearance still works without storage. */
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
