import { useMemo, type ComponentProps } from 'react';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';

const supportedTimezones = Intl.supportedValuesOf('timeZone');

type TimezoneSelectProps = Pick<
  ComponentProps<typeof SelectTrigger>,
  'id' | 'ref' | 'onBlur' | 'aria-invalid' | 'aria-describedby'
> & {
  name: string;
  value?: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
};

export function TimezoneSelect({
  name,
  value,
  onValueChange,
  disabled,
  ...triggerProps
}: TimezoneSelectProps) {
  const options = useMemo(() => {
    // Saved aliases may be valid even when the browser does not list them.
    const zones = new Set(supportedTimezones);
    if (value) zones.add(value);
    zones.delete('UTC');

    return ['UTC', ...[...zones].sort()].map((zone) => ({
      value: zone,
      label: zone,
    }));
  }, [value]);

  return (
    <Select
      name={name}
      value={value || null}
      items={options}
      disabled={disabled}
      onValueChange={(zone) => {
        if (zone !== null) onValueChange(zone);
      }}
    >
      <SelectTrigger className="w-full" {...triggerProps}>
        <SelectValue placeholder="Choose a timezone…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
