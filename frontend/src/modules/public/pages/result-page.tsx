import { Link, useLocation, useSearch } from '@tanstack/react-router';
import { CircleCheck, CircleX } from 'lucide-react';

import { Button } from '@/common/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';

const messages: Record<
  string,
  { title: string; description: string; success: boolean }
> = {
  unavailable: {
    title: 'Zoom is not available',
    description:
      'Zoom is not configured for this deployment. Contact your workspace administrator.',
    success: false,
  },
  success: {
    title: 'You are all set',
    description: 'Your request has been completed.',
    success: true,
  },
  connected: {
    title: 'Account connected',
    description: 'You can return to Morgenruf.',
    success: true,
  },
  subscribed: {
    title: 'Email updates enabled',
    description: 'You will receive future standup email updates.',
    success: true,
  },
  unsubscribed: {
    title: 'Email updates stopped',
    description: 'You have been unsubscribed from these standup email updates.',
    success: true,
  },
  invalid: {
    title: 'This link is not valid',
    description:
      'The link may have expired. Please use the latest message or contact your workspace administrator.',
    success: false,
  },
  expired: {
    title: 'This link has expired',
    description: 'Request a new link and try again.',
    success: false,
  },
  denied: {
    title: 'Connection cancelled',
    description: 'You can try connecting again when you are ready.',
    success: false,
  },
  error: {
    title: 'Something went wrong',
    description: 'We could not complete your request. Please try again.',
    success: false,
  },
};

export default function ResultPage() {
  const params = useSearch({ strict: false });
  const location = useLocation();

  const status = params.status ?? params.result ?? 'error';
  const result = messages[status] ?? messages.error;

  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <Card className="w-full max-w-md py-6">
        <CardHeader className="items-center text-center">
          {result.success ? (
            <CircleCheck className="mb-3 size-9 text-success" />
          ) : (
            <CircleX className="mb-3 size-9 text-destructive" />
          )}
          <CardTitle className="text-xl">
            <h1>{result.title}</h1>
          </CardTitle>
        </CardHeader>

        <CardContent className="space-y-5 text-center">
          <p className="text-sm text-muted-foreground">{result.description}</p>
          {location.pathname.startsWith('/connect/') && result.success && (
            <p className="text-sm text-muted-foreground">
              Your Zoom account can now be used for coffee chats.
            </p>
          )}
          <Button
            nativeButton={false}
            role="link"
            render={<Link to="/dashboard/standups" />}
          >
            Return to Morgenruf
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
