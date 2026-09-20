import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect } from 'vitest';

export async function chooseOption(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
  option: string,
) {
  const trigger = await screen.findByRole('combobox', { name });
  await user.click(trigger);
  await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'true'));
  const listbox = await screen.findByRole('listbox');
  await waitFor(() => expect(listbox).toBeVisible());
  await user.click(
    await within(listbox).findByRole('option', { name: option }),
  );
  await waitFor(() =>
    expect(trigger).toHaveAttribute('aria-expanded', 'false'),
  );
}
