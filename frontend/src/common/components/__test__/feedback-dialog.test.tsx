import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { createApplicationServices } from '@/common/api/services';
import { ServicesProvider } from '@/common/api/services-context';

import { FeedbackDialog } from '../feedback-dialog';

function setup(response: Response) {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(response);
  const services = createApplicationServices({ fetch });
  const onOpenChange = vi.fn();

  render(
    <ServicesProvider services={services}>
      <QueryClientProvider client={services.queryClient}>
        <FeedbackDialog open onOpenChange={onOpenChange} />
      </QueryClientProvider>
    </ServicesProvider>,
  );

  return { fetch, onOpenChange };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

describe('feedback dialog', () => {
  it('sends the chosen kind, title, details and page', async () => {
    const { fetch, onOpenChange } = setup(json({ ok: true }));

    expect(screen.getByRole('radio', { name: /Report a bug/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    await userEvent.click(
      screen.getByRole('radio', { name: /Suggest an improvement/ }),
    );
    await userEvent.type(screen.getByLabelText('Title'), 'Dark mode please');
    await userEvent.type(screen.getByLabelText('Details'), 'Easier at night');
    await userEvent.click(
      screen.getByRole('button', { name: 'Send feedback' }),
    );

    await vi.waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    const [url, init] = fetch.mock.calls[0];
    expect(String(url)).toContain('/dashboard/api/feedback');
    expect(JSON.parse(String(init?.body))).toEqual({
      kind: 'idea',
      title: 'Dark mode please',
      details: 'Easier at night',
      page: '/',
    });
  });

  it('needs a title before sending', async () => {
    const { fetch } = setup(json({ ok: true }));

    await userEvent.click(
      screen.getByRole('button', { name: 'Send feedback' }),
    );

    expect(await screen.findByText('Add a short title.')).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows the server error and stays open', async () => {
    const { onOpenChange } = setup(
      json(
        { error: 'Could not send your feedback. Try again in a minute.' },
        502,
      ),
    );

    await userEvent.type(screen.getByLabelText('Title'), 'Broken page');
    await userEvent.click(
      screen.getByRole('button', { name: 'Send feedback' }),
    );

    expect(
      await screen.findByText(/Could not send your feedback/),
    ).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
