import { useId, useState } from 'react';
import { Search } from 'lucide-react';

import { useMemberDirectory } from '@/common/api/use-member-directory';
import { Checkbox } from '@/common/components/ui/checkbox';
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from '@/common/components/ui/input-group';
import { ScrollArea } from '@/common/components/ui/scroll-area';

export const MAX_MANAGERS = 10;

/**
 * Who may change this one standup without administering every standup.
 * Shown to Standups admins only; a manager cannot name other managers.
 */
export function ManagersField({
  value,
  onChange,
  disabled,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const [search, setSearch] = useState('');
  const directory = useMemberDirectory();
  const query = search.trim().toLowerCase();
  const people = (directory.data ?? []).filter(
    (person) =>
      !query ||
      [person.name, person.display_name, person.email, person.id]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(query),
  );
  const full = value.length >= MAX_MANAGERS;

  return (
    <fieldset className="space-y-3">
      <legend className="mb-0 text-sm font-medium">Managers</legend>
      <p className="text-sm text-muted-foreground">
        Managers can change this standup&apos;s questions, schedule and
        participants, and pause it. They cannot delete it, move it to another
        channel or change other standups.
      </p>
      <InputGroup className="h-9">
        <InputGroupAddon>
          <Search aria-hidden="true" />
        </InputGroupAddon>
        <InputGroupInput
          aria-label="Search managers"
          placeholder="Search people…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </InputGroup>
      <p className="text-xs text-muted-foreground" role="status">
        {value.length
          ? `${value.length} manager${value.length === 1 ? '' : 's'}${full ? ` (the most a standup can have)` : ''}`
          : 'No managers: only admins can change it'}
      </p>
      <ScrollArea
        className="max-h-44 rounded-lg border"
        contentClassName="grid gap-2 p-2 sm:grid-cols-2"
        viewportProps={{ role: 'region', 'aria-label': 'Managers' }}
      >
        {!people.length && (
          <p className="px-3 py-4 text-center text-sm text-muted-foreground sm:col-span-2">
            {directory.isPending ? 'Loading people…' : 'Nobody matches.'}
          </p>
        )}
        {people.map((person) => {
          const checked = value.includes(person.id);

          return (
            <label
              key={person.id}
              className="flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border p-2 text-sm has-data-checked:border-primary has-data-checked:bg-primary/5"
            >
              <Checkbox
                aria-labelledby={`${id}-${person.id}`}
                checked={checked}
                disabled={disabled || (!checked && full)}
                onCheckedChange={(next) =>
                  onChange(
                    next
                      ? [...value, person.id]
                      : value.filter((id) => id !== person.id),
                  )
                }
              />
              <span id={`${id}-${person.id}`} className="truncate">
                <span className="sr-only">Make manager: </span>
                {person.name || person.id}
              </span>
            </label>
          );
        })}
      </ScrollArea>
    </fieldset>
  );
}
