import { useState } from 'react';

export function Person({
  name,
  avatar,
  detail,
}: {
  name: string;
  avatar?: string | null;
  detail?: string;
}) {
  const [broken, setBroken] = useState(false);

  const initials = name
    .split(/\s+/)
    .map((word) => word[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-full bg-muted text-xs font-medium">
        {avatar && !broken ? (
          <img
            src={avatar}
            alt=""
            loading="lazy"
            className="size-full object-cover"
            onError={() => setBroken(true)}
          />
        ) : (
          initials
        )}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{name}</span>
        {detail && (
          <span className="block text-xs text-muted-foreground">{detail}</span>
        )}
      </span>
    </span>
  );
}
