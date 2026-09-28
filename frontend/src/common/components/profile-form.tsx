import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactNode,
} from 'react';
import { Controller, useForm } from 'react-hook-form';

import type {
  MemberProfile,
  MemberProfileRecord,
} from '@/common/api/generated/data-contracts';
import { Button } from '@/common/components/ui/button';
import { Input } from '@/common/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/common/components/ui/select';
import { Textarea } from '@/common/components/ui/textarea';
import { applyApiErrors } from '@/common/forms/api-errors';
import {
  isRealBirthday,
  months,
  profileFormValues,
  profileInput,
  profileLimits,
  type ProfileFormValues,
} from '@/common/lib/profile';

const monthOptions = [
  { value: '', label: 'Not set' },
  ...months.map((month, index) => ({ value: String(index + 1), label: month })),
];

const dayOptions = [
  { value: '', label: 'Not set' },
  ...Array.from({ length: 31 }, (_, index) => ({
    value: String(index + 1),
    label: String(index + 1),
  })),
];

function Field({
  label,
  children,
  help,
  error,
}: {
  label: string;
  children: ReactNode;
  help?: string;
  error?: string;
}) {
  const id = useId();

  return (
    <div className="flex flex-col gap-2 text-sm font-medium">
      <label htmlFor={id}>{label}</label>
      {Children.map(children, (child, index) =>
        index === 0 &&
        isValidElement<{ id?: string; 'aria-describedby'?: string }>(child)
          ? cloneElement(child, {
              id,
              'aria-describedby': help ? `${id}-help` : undefined,
            })
          : child,
      )}
      {help && (
        <p
          id={`${id}-help`}
          className="text-xs font-normal text-muted-foreground"
        >
          {help}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm font-normal text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * One form for a profile, used by a member on their own page and by an admin
 * editing someone else's. The server validates too; its field errors land on
 * the same inputs.
 */
export function ProfileForm({
  profile,
  onSave,
  pending,
  submitLabel = 'Save profile',
  secondaryAction,
}: {
  profile: MemberProfileRecord | undefined;
  onSave: (input: MemberProfile) => Promise<unknown>;
  pending: boolean;
  submitLabel?: string;
  secondaryAction?: ReactNode;
}) {
  const form = useForm<ProfileFormValues>({
    resetOptions: { keepDirtyValues: true },
    values: profileFormValues(profile),
  });
  const { errors } = form.formState;

  return (
    <form
      className="space-y-5"
      onSubmit={form.handleSubmit(async (values) => {
        try {
          await onSave(profileInput(values));
        } catch (error) {
          applyApiErrors(error, form.setError);
        }
      })}
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Birthday</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Controller
            control={form.control}
            name="birth_month"
            render={({ field }) => (
              <Select
                name={field.name}
                value={field.value}
                items={monthOptions}
                disabled={pending}
                onValueChange={(value) => field.onChange(value ?? '')}
              >
                <SelectTrigger
                  className="w-full"
                  aria-label="Birthday month"
                  ref={field.ref}
                  onBlur={field.onBlur}
                  aria-invalid={!!errors.birth_month}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {monthOptions.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <Controller
            control={form.control}
            name="birth_day"
            rules={{
              validate: (day) =>
                isRealBirthday(form.getValues('birth_month'), day) ||
                'That day does not exist in that month.',
            }}
            render={({ field }) => (
              <Select
                name={field.name}
                value={field.value}
                items={dayOptions}
                disabled={pending}
                onValueChange={(value) => field.onChange(value ?? '')}
              >
                <SelectTrigger
                  className="w-full"
                  aria-label="Birthday day"
                  ref={field.ref}
                  onBlur={field.onBlur}
                  aria-invalid={!!errors.birth_day}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {dayOptions.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Only the day and month are kept, never the year.
        </p>
        {(errors.birth_day ?? errors.birth_month) && (
          <p role="alert" className="text-sm text-destructive">
            {(errors.birth_day ?? errors.birth_month)?.message}
          </p>
        )}
      </fieldset>

      <Field
        label="Started on"
        help="The day you joined. Leave it empty if you would rather not say."
        error={errors.start_date?.message}
      >
        <Input
          type="date"
          disabled={pending}
          {...form.register('start_date')}
        />
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Role" error={errors.role?.message}>
          <Input
            maxLength={profileLimits.role}
            placeholder="Backend engineer"
            disabled={pending}
            {...form.register('role', { maxLength: profileLimits.role })}
          />
        </Field>
        <Field label="Location" error={errors.location?.message}>
          <Input
            maxLength={profileLimits.location}
            placeholder="Berlin"
            disabled={pending}
            {...form.register('location', {
              maxLength: profileLimits.location,
            })}
          />
        </Field>
      </div>

      <Field
        label="Ask me about"
        help={`Up to ${profileLimits.ask_me_about} characters.`}
        error={errors.ask_me_about?.message}
      >
        <Textarea
          maxLength={profileLimits.ask_me_about}
          placeholder="Rust, bouldering, sourdough"
          disabled={pending}
          {...form.register('ask_me_about', {
            maxLength: profileLimits.ask_me_about,
          })}
        />
      </Field>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          disabled={pending}
          {...form.register('dont_celebrate')}
        />
        Don’t celebrate me publicly
      </label>

      {errors.root?.server && (
        <p role="alert" className="text-sm text-destructive">
          {errors.root.server.message}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
        {secondaryAction}
      </div>
    </form>
  );
}
