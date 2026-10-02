import { getRouteApi } from '@tanstack/react-router';

import { ThemeToggle } from '@/common/components/theme-toggle';
import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';

export default function LoginPage() {
  const params = getRouteApi('/dashboard/login').useSearch();

  return (
    <div className="grid min-h-dvh place-items-center px-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-sm">
        <div className="mb-7 flex items-center justify-center gap-2">
          <img
            src="/static/icon-192.png"
            alt=""
            className="size-10 rounded-lg"
          />
          <span className="text-lg font-semibold">Morgenruf</span>
        </div>

        <Card className="py-6">
          <CardHeader className="px-6 text-center">
            <CardTitle className="text-xl">
              <h1>Your team's morning call</h1>
            </CardTitle>
            <CardDescription className="mt-2 text-sm">
              Your standups, coffee chats and recognition, managed from Slack.
            </CardDescription>
          </CardHeader>
          <CardContent className="mt-3 px-6">
            {params.error === 'invalid-link' && (
              <p
                role="alert"
                className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive"
              >
                This sign-in link has expired or was already used. Get a new one
                from Morgenruf in Slack: click Dashboard on the Home tab, or
                type <code>/morgenruf dashboard</code>.
              </p>
            )}

            {params.error === 'open-in-slack' && (
              <p role="alert" className="mb-4 rounded-md bg-muted p-3 text-sm">
                Open the Morgenruf app in your Slack workspace (Apps in the
                sidebar), then click Dashboard on its Home tab.
              </p>
            )}

            <Button
              nativeButton={false}
              role="link"
              render={<a href="/dashboard/open-in-slack" />}
              className="h-10 w-full"
            >
              Open Morgenruf in Slack
            </Button>

            <p className="mt-3 text-center text-sm leading-relaxed text-muted-foreground">
              Then click <strong>Dashboard</strong> on the app&apos;s Home tab,
              or type <code>/morgenruf dashboard</code> anywhere. You get a
              sign-in link of your own, no admin needed.
            </p>

            <p className="mt-6 border-t pt-4 text-center text-xs leading-relaxed text-muted-foreground">
              Adding Morgenruf to a new workspace?{' '}
              <a href="/install" className="text-primary underline">
                Install it with Slack
              </a>
              . Installing may need a Slack admin&apos;s approval.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
