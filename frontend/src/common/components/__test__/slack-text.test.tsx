import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SlackText } from '../slack-text';

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

  it('decodes Slack link destinations and labels exactly once', () => {
    render(
      <SlackText
        text={
          '<https://example.com/report?id=42&amp;view=detail|R&amp;D &lt;report&gt;> <https://example.com/?literal=&amp;amp;>'
        }
      />,
    );

    const report = screen.getByRole('link', { name: 'R&D <report>' });
    expect(report).toHaveAttribute(
      'href',
      'https://example.com/report?id=42&view=detail',
    );
    expect(new URL(report.getAttribute('href')!).searchParams.get('view')).toBe(
      'detail',
    );
    expect(
      screen.getByRole('link', {
        name: 'https://example.com/?literal=&amp;',
      }),
    ).toHaveAttribute('href', 'https://example.com/?literal=&amp;');
  });

  it('decodes text and formatting without interpreting escaped HTML', () => {
    const { container } = render(
      <SlackText
        text={
          '&amp;lt;literal&amp;gt; *R&amp;D* `a &lt; b` <#C1|R&amp;D> <@U1|Tom &amp; Sam> &lt;img src=x onerror=alert(1)&gt; &lt;javascript:alert(1)|Run&gt;'
        }
      />,
    );

    expect(container.textContent).toContain('&lt;literal&gt;');
    expect(container.querySelector('strong')).toHaveTextContent('R&D');
    expect(container.querySelector('code')).toHaveTextContent('a < b');
    expect(screen.getByText('#R&D')).toBeInTheDocument();
    expect(screen.getByText('@Tom & Sam')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
