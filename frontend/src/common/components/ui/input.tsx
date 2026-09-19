import * as React from 'react';
import { useState } from 'react';
import { Input as InputPrimitive } from '@base-ui/react/input';
import { Eye, EyeOff, Search } from 'lucide-react';

import { cn } from '@/common/lib/utils';

import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from './input-group';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        'h-9 w-full min-w-0 rounded-md border border-input bg-input/20 px-2 py-0.5 text-sm transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-xs/relaxed file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 md:text-xs/relaxed dark:bg-input/30 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40',
        className,
      )}
      {...props}
    />
  );
}

export { Input };

type SearchInputProps = Omit<React.ComponentProps<'input'>, 'type'> & {
  className?: string;
};

export const SearchInput = ({
  placeholder = 'Search...',
  className,
  ...props
}: SearchInputProps) => {
  return (
    <InputGroup className={cn('w-full flex-1', className)}>
      <InputGroupInput {...props} placeholder={placeholder} />
      <InputGroupAddon>
        <Search />
      </InputGroupAddon>
    </InputGroup>
  );
};

type PasswordInputProps = Omit<React.ComponentProps<'input'>, 'type'> & {
  className?: string;
};

export const PasswordInput = ({ className, ...props }: PasswordInputProps) => {
  const [visible, setVisible] = useState(false);

  return (
    <InputGroup className={cn('w-full', className)}>
      <InputGroupInput type={visible ? 'text' : 'password'} {...props} />
      <InputGroupAddon align="inline-end">
        <InputGroupButton
          type="button"
          size="icon-xs"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
        >
          {visible ? <EyeOff /> : <Eye />}
          <span className="sr-only">
            {visible ? 'Hide password' : 'Show password'}
          </span>
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>
  );
};
