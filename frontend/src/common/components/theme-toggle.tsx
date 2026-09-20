import { Check, Moon, Sun } from 'lucide-react';

import { useTheme, type Theme } from '@/common/providers/theme-context';

import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Choose appearance" />
        }
      >
        <Sun className="size-4 dark:hidden" />
        <Moon className="hidden size-4 dark:block" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {(['light', 'dark', 'system'] satisfies Theme[]).map((value) => (
          <DropdownMenuItem key={value} onClick={() => setTheme(value)}>
            {value[0].toUpperCase() + value.slice(1)}
            {theme === value && <Check className="size-4 ms-auto" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
