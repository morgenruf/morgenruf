import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CsvInput } from '../csv-input';

const example = 'date,name\n2026-12-25,Christmas Day';

function Example({ onText = () => {} }: { onText?: (text: string) => void }) {
  const [csv, setCsv] = useState('');

  return (
    <CsvInput
      id="t"
      value={csv}
      example={example}
      templateName="holidays-template.csv"
      onChange={(text) => {
        setCsv(text);
        onText(text);
      }}
    />
  );
}

afterEach(() => vi.restoreAllMocks());

describe('CSV input', () => {
  it('downloads the example as a template file', async () => {
    const created = vi.fn<(blob: Blob) => string>(() => 'blob:template');
    URL.createObjectURL = created as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(this.download).toBe('holidays-template.csv');
      });

    render(<Example />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Download template' }),
    );

    expect(click).toHaveBeenCalledTimes(1);
    expect(await created.mock.calls[0][0].text()).toBe(`${example}\n`);
  });

  it('reads a chosen file and shows its name', async () => {
    const onText = vi.fn();
    render(<Example onText={onText} />);

    const file = new File(['date,name\n2027-01-01,New Year'], 'days.csv', {
      type: 'text/csv',
    });
    await userEvent.upload(screen.getByLabelText(/Drop a CSV file/), file);

    expect(await screen.findByText('days.csv')).toBeInTheDocument();
    expect(onText).toHaveBeenCalledWith('date,name\n2027-01-01,New Year');
    expect(screen.getByLabelText('CSV')).toHaveValue(
      'date,name\n2027-01-01,New Year',
    );
  });

  it('shows the example only as a placeholder', () => {
    render(<Example />);
    const box = screen.getByLabelText('CSV');
    expect(box).toHaveValue('');
    expect(box).toHaveAttribute('placeholder', example);
  });
});
