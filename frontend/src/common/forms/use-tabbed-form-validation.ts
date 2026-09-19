import { useLayoutEffect, useState, type FormEvent } from 'react';
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

type FormControl = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

function isFormControl(element: EventTarget): element is FormControl {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLSelectElement ||
    element instanceof HTMLTextAreaElement
  );
}

/** Reveal native validation errors before focusing a field in a hidden panel. */
export function useTabbedFormValidation<
  Values extends FieldValues,
  Tab extends string,
>(
  tabs: readonly Tab[],
  setTab: (tab: Tab) => void,
  setError: UseFormSetError<Values>,
) {
  const [invalid, setInvalid] = useState<{ field: FormControl } | null>(null);

  useLayoutEffect(() => {
    invalid?.field.focus();
  }, [invalid]);

  return (event: FormEvent<HTMLFormElement>) => {
    // Native validation still blocks submission; replace its focus/bubble with
    // the form's visible error message and focus after the panel has rendered.
    event.preventDefault();
    const field = event.target;
    if (!isFormControl(field)) return;

    // Browsers fire invalid for every failing field. Keep the first one visible.
    const firstInvalid = Array.from(event.currentTarget.elements).find(
      (element) =>
        isFormControl(element) &&
        element.willValidate &&
        !element.validity.valid,
    );
    if (field !== firstInvalid) return;

    const panel = field.closest<HTMLElement>('[role="tabpanel"]');
    const tab = tabs.find((name) => name === panel?.dataset.tab);
    if (tab) setTab(tab);
    setError((field.name || 'root.server') as Path<Values>, {
      type: 'native',
      message: field.validationMessage,
    });
    setInvalid({ field });
  };
}
