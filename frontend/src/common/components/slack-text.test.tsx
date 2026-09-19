import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SlackText } from './slack-text';

describe('Slack text rendering', () => {
  it('resolves member/channel references and supports safe external links', () => {
    render(
      <SlackText
        text="Hi <@U1>, see <#C1> and <https://example.com|the plan>."
        members={{ U1: 'Ada' }}
        channels={{ C1: 'general' }}
      />,
    );

    expect(screen.getByText('@Ada')).toBeInTheDocument();
    expect(screen.getByText('#general')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'the plan' })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );
  });

  it('never interprets HTML or javascript links from a response', () => {
    const { container } = render(
      <SlackText
        text={'<img src=x onerror=alert(1)> <javascript:alert(1)|Run>'}
      />,
    );

    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('<img');
  });
});
