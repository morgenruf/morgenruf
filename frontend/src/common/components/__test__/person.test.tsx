import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Person } from '../person';

describe('person identity', () => {
  it('keeps the full name visible and initials decorative when no photo exists', () => {
    const name = '  Ada   Lovelace  ';
    const { container } = render(
      <Person name={name} detail="Engineering" size="compact" />,
    );
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(screen.getByText('AL')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('Engineering')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });

  it('falls back on image error and retries when the photo URL changes', () => {
    const { container, rerender } = render(
      <Person name="Ada Lovelace" avatar="/old-photo.png" />,
    );
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('AL')).toBeInTheDocument();

    rerender(<Person name="Ada Lovelace" avatar="/new-photo.png" />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/new-photo.png',
    );
    expect(container.querySelector('img')).toHaveAttribute('alt', '');
    expect(screen.queryByText('AL')).not.toBeInTheDocument();
  });

  it('handles a blank fallback name without throwing', () => {
    render(<Person name="   " />);
    expect(screen.getByText('?')).toBeInTheDocument();
  });
});
