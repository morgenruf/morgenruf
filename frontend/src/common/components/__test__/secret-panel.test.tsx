import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SecretPanel } from '../secret-panel';

function Example() {
  const [secret, setSecret] = useState<string | null>('one-time-test-secret');

  return (
    <SecretPanel
      title="Copy your signing secret"
      value={secret}
      onDismiss={() => setSecret(null)}
    />
  );
}

describe('one-time secrets', () => {
  it('removes the raw value from the DOM when dismissed', async () => {
    render(<Example />);

    expect(screen.getByTestId('one-time-secret')).toHaveTextContent(
      'one-time-test-secret',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Done' }));

    expect(screen.queryByText('one-time-test-secret')).not.toBeInTheDocument();
  });

  it('clears the value when closed with Escape', async () => {
    render(<Example />);

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByText('one-time-test-secret')).not.toBeInTheDocument();
  });
});
