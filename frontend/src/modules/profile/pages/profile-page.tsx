import { toast } from 'sonner';

import { LoadingTransition } from '@/common/components/loading-transition';
import { ErrorState, PageHeader } from '@/common/components/page';
import { ProfileForm } from '@/common/components/profile-form';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/common/components/ui/card';

import { useMyProfile } from '../hooks';
import { ProfileFormSkeleton } from '../loading';

export default function ProfilePage() {
  const { profile, save } = useMyProfile();

  return (
    <div className="page">
      <PageHeader
        title="My profile"
        description="What your team sees about you in Morgenruf."
      />

      <Card>
        <CardHeader>
          <CardTitle>About you</CardTitle>
          <CardDescription>
            Your birthday and start date let the team celebrate with you. Your
            role, location and what to ask you about help new people get to know
            you. You can change this any time, here or with{' '}
            <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">
              /morgenruf profile
            </code>{' '}
            in Slack.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {profile.isError ? (
            <ErrorState
              error={profile.error}
              retry={() => void profile.refetch()}
            />
          ) : (
            <LoadingTransition pending={profile.isPending}>
              {profile.isPending ? (
                <ProfileFormSkeleton />
              ) : (
                <div className="max-w-2xl space-y-4">
                  {profile.data?.set_by_admin && (
                    <p className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
                      An admin filled in some of this. Check it, and correct
                      anything that is wrong.
                    </p>
                  )}
                  <ProfileForm
                    profile={profile.data}
                    pending={save.isPending}
                    onSave={(input) =>
                      save.mutateAsync(input).then(() => {
                        toast.success('Profile saved');
                      })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Only the day and month of your birthday are stored. If you
                    leave the workspace, your profile is deleted after 30 days.
                  </p>
                </div>
              )}
            </LoadingTransition>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
