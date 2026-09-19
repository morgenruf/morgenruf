import { Fragment, type ReactNode } from 'react';

function decodeSlackEntities(value: string) {
  // Decode only Slack's three entities, in one pass so &amp;lt; stays &lt;.
  return value.replace(/&(amp|lt|gt);/g, (entity) =>
    entity === '&amp;' ? '&' : entity === '&lt;' ? '<' : '>',
  );
}

/** Render Slack text as React nodes; user-provided HTML is never interpreted. */
export function SlackText({
  text,
  members = {},
  channels = {},
}: {
  text?: string | null;
  members?: Record<string, string>;
  channels?: Record<string, string>;
}) {
  if (!text) return <span className="text-muted-foreground">—</span>;

  const pieces = text.split(/(<[^>]+>|\*[^*\n]+\*|`[^`\n]+`)/g);

  return (
    <span className="whitespace-pre-wrap break-words">
      {pieces.map((piece, index) => {
        let content: ReactNode = decodeSlackEntities(piece);
        const user = piece.match(/^<@([^>|]+)(?:\|([^>]+))?>$/);
        const channel = piece.match(/^<#([^>|]+)(?:\|([^>]+))?>$/);
        const link = piece.match(/^<(https?:\/\/[^>|]+)(?:\|([^>]+))?>$/);

        if (user)
          content = (
            <span className="font-medium">
              @{members[user[1]] ?? decodeSlackEntities(user[2] ?? user[1])}
            </span>
          );
        else if (channel)
          content = (
            <span className="font-medium">
              #
              {channels[channel[1]] ??
                decodeSlackEntities(channel[2] ?? channel[1])}
            </span>
          );
        else if (link)
          content = (
            <a
              href={decodeSlackEntities(link[1])}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2"
            >
              {decodeSlackEntities(link[2] ?? link[1])}
            </a>
          );
        else if (piece.startsWith('*') && piece.endsWith('*'))
          content = <strong>{decodeSlackEntities(piece.slice(1, -1))}</strong>;
        else if (piece.startsWith('`') && piece.endsWith('`'))
          content = (
            <code className="rounded bg-muted px-1 text-xs">
              {decodeSlackEntities(piece.slice(1, -1))}
            </code>
          );
        return <Fragment key={index}>{content}</Fragment>;
      })}
    </span>
  );
}
