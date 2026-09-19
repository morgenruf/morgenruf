import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

export async function chooseOption(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
  option: string,
) {
  await user.click(screen.getByRole('combobox', { name }));
  await user.click(await screen.findByRole('option', { name: option }));
}
