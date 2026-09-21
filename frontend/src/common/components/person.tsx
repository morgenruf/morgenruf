import { useState } from 'react';

import { cn } from '@/common/lib/utils';

type PersonSize = 'compact' | 'standard' | 'large';

const avatarSizes: Record<PersonSize, string> = {
  compact: 'size-6 text-[10px]',
  standard: 'size-8 text-xs',
  large: 'size-11 text-sm',
};

function AvatarContent({
  name,
  avatar,
}: {
  name: string;
  avatar?: string | null;
}) {
  const [broken, setBroken] = useState(false);

  if (avatar && !broken)
    return (
      <img
        src={avatar}
        alt=""
        loading="lazy"
        className="size-full object-cover"
        onError={() => setBroken(true)}
      />
    );

  return (
    name
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((word) => Array.from(word)[0])
      .join('')
      .toUpperCase() || '?'
  );
}

export function PersonAvatar({
  name,
  avatar,
  size = 'standard',
}: {
  name: string;
  avatar?: string | null;
  size?: PersonSize;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden rounded-full bg-primary/10 font-medium text-primary',
        avatarSizes[size],
      )}
    >
      <AvatarContent key={avatar ?? ''} name={name} avatar={avatar} />
    </span>
  );
}

export function Person({
  name,
  avatar,
  detail,
  size = 'standard',
  className,
}: {
  name: string;
  avatar?: string | null;
  detail?: string;
  size?: PersonSize;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex min-w-0 max-w-full items-center gap-2 align-middle',
        className,
      )}
    >
      <PersonAvatar name={name} avatar={avatar} size={size} />
      <span className="min-w-0 whitespace-normal wrap-anywhere">
        <span
          className={cn(
            'block font-medium',
            size === 'compact' ? 'text-xs' : 'text-sm',
          )}
        >
          {name}
        </span>
        {detail && (
          <span className="block text-xs text-muted-foreground">{detail}</span>
        )}
      </span>
    </span>
  );
}
