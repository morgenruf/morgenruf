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
              Sign in with Slack to manage standups, coffee chats, and
              recognition in your workspace.
            </CardDescription>
          </CardHeader>
          <CardContent className="mt-3 px-6">
            {params.error === 'invalid-link' && (
              <p
                role="alert"
                className="mb-4 rounded-md bg-destructive/10 p-3 text-sm text-destructive"
              >
                This sign-in link is invalid or has expired. Sign in with Slack
                to continue.
              </p>
            )}

            <Button
              nativeButton={false}
              role="link"
              render={<a href="/install" />}
              className="h-10 w-full"
            >
              Continue with Slack
            </Button>

            <p className="mt-4 text-center text-xs leading-relaxed text-muted-foreground">
              Morgenruf uses your Slack workspace to sign you in. Your workspace
              permissions determine what you can manage.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
