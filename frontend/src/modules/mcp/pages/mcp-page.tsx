import { useState } from 'react';
import { Copy, KeyRound, Plus } from 'lucide-react';
import { toast } from 'sonner';

import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '@/common/components/page';
import { SecretPanel } from '@/common/components/secret-panel';
import { Badge } from '@/common/components/ui/badge';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/common/components/ui/dialog';
import { Input } from '@/common/components/ui/input';
import { Label } from '@/common/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { formatDate, relativeTime } from '@/common/lib/format';

import { buildMcpConfig } from '../config';
import { useMcp } from '../hooks';

const assistantOptions = [
  { value: 'claude', label: 'Claude Desktop' },
  { value: 'cursor', label: 'Cursor' },
  { value: 'vscode', label: 'VS Code' },
  { value: 'http', label: 'HTTP / curl' },
];

export default function McpPage() {
  const { keys, create, revoke, session, canEdit } = useMcp();

  const [newKey, setNewKey] = useState(false);
  const [name, setName] = useState('');
  const [secret, setSecret] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [assistant, setAssistant] = useState('claude');

  const endpoint = session?.mcp_endpoint ?? '';
  const config = buildMcpConfig(assistant, endpoint);

  return (
    <div className="page">
      <PageHeader
        title="MCP"
        description="Give your AI assistant scoped access to your team’s standup data."
        actions={
          canEdit && (
            <Button
              onClick={() => {
                setName('');
                setNewKey(true);
              }}
            >
              <Plus /> Generate key
            </Button>
          )
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>Workspace connection</CardTitle>
          <CardDescription>
            Use this deployment’s remote endpoint with a workspace API key.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            Endpoint:{' '}
            <code className="break-all rounded bg-muted px-2 py-1">
              {endpoint}
            </code>
          </p>
          <div className="flex items-center gap-2">
            <p>
              Workspace: <code>{session?.team_id}</code>
            </p>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Copy workspace ID"
              onClick={() =>
                void navigator.clipboard.writeText(session?.team_id ?? '').then(
                  () => toast.success('Workspace ID copied'),
                  () => toast.error('Could not copy workspace ID'),
                )
              }
            >
              <Copy className="size-3.5" />
            </Button>
          </div>
          <a
            className="text-primary underline underline-offset-4"
            href="https://docs.morgenruf.dev/mcp.html"
            target="_blank"
            rel="noreferrer"
          >
            MCP setup guide
          </a>
          <a
            className="ml-4 text-primary underline underline-offset-4"
            href="https://docs.morgenruf.dev/mcp.html#available-tools"
            target="_blank"
            rel="noreferrer"
          >
            Available tools
          </a>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>API keys</CardTitle>
          <CardDescription>
            Keys can access this workspace. Raw keys are shown only when
            created.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {keys.isPending ? (
            <LoadingState />
          ) : keys.isError ? (
            <ErrorState error={keys.error} retry={() => void keys.refetch()} />
          ) : !keys.data?.keys.length ? (
            <EmptyState
              title="No API keys yet"
              description="Generate a key to connect an assistant."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="p-3">Name</th>
                    <th className="p-3">Prefix</th>
                    <th className="p-3">Created</th>
                    <th className="p-3">Last used</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {keys.data.keys.map((key) => (
                    <tr key={key.id} className="border-b last:border-0">
                      <td className="p-3 font-medium">
                        {key.name || 'Default'}
                      </td>
                      <td className="p-3">
                        <code>{key.key_prefix}…</code>
                      </td>
                      <td className="whitespace-nowrap p-3">
                        {formatDate(key.created_at)}
                      </td>
                      <td className="whitespace-nowrap p-3">
                        {key.last_used_at
                          ? relativeTime(key.last_used_at)
                          : 'Never'}
                      </td>
                      <td className="p-3">
                        <Badge variant={key.active ? 'secondary' : 'outline'}>
                          {key.active ? 'Active' : 'Revoked'}
                        </Badge>
                      </td>
                      <td className="p-3">
                        {canEdit && key.active && (
                          <Button
                            variant="destructive"
                            disabled={revoke.isPending}
                            onClick={() => setDeleting(key.id)}
                          >
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Connect an assistant</CardTitle>
          <CardDescription>
            Copy the configuration and replace the placeholder with your key.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select
            items={assistantOptions}
            value={assistant}
            onValueChange={(value) => {
              if (value !== null) setAssistant(value);
            }}
          >
            <SelectTrigger aria-label="Assistant" className="w-full max-w-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {assistantOptions.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="break-all text-xs text-muted-foreground">
            {assistant === 'http'
              ? 'Run in a terminal to list available tools.'
              : assistant === 'cursor'
                ? '~/.cursor/mcp.json'
                : assistant === 'vscode'
                  ? '.vscode/mcp.json'
                  : navigator.platform.includes('Win')
                    ? '%APPDATA%\\Claude\\claude_desktop_config.json'
                    : '~/Library/Application Support/Claude/claude_desktop_config.json'}
          </p>
          <pre className="overflow-x-auto rounded-lg border bg-muted p-4 text-xs">
            <code>{config}</code>
          </pre>
          <Button
            variant="outline"
            onClick={() =>
              void navigator.clipboard.writeText(config).then(
                () => toast.success('Configuration copied'),
                () => toast.error('Could not copy configuration'),
              )
            }
          >
            <Copy /> Copy configuration
          </Button>
        </CardContent>
      </Card>
      <Dialog open={newKey} onOpenChange={setNewKey}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate an API key</DialogTitle>
            <DialogDescription>
              Give the key a name so you can identify it later.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate({
                name: name.trim() || 'Default',
                receive: (value) => {
                  setSecret(value);
                  setNewKey(false);
                },
              });
            }}
          >
            <Label htmlFor="key-name">Key name</Label>
            <Input
              id="key-name"
              placeholder="My assistant"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <Button type="submit" disabled={create.isPending}>
              <KeyRound />
              {create.isPending ? 'Generating…' : 'Generate key'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
      <SecretPanel
        title="Copy your API key"
        value={secret}
        onDismiss={() => {
          setSecret(null);
          create.reset();
        }}
      />
      <Dialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke this key?</DialogTitle>
            <DialogDescription>
              Assistants using this key will lose access immediately.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={revoke.isPending}
              onClick={() => {
                if (deleting !== null)
                  revoke.mutate(deleting, {
                    onSuccess: () => {
                      setDeleting(null);
                      toast.success('Key revoked');
                    },
                  });
              }}
            >
              Revoke key
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
