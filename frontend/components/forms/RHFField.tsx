import type { ReactNode } from "react";

import { FieldWrapper } from "./FieldWrapper";

interface RHFFieldState {
  error?: {
    message?: string;
  };
}

export interface RHFFieldControl {
  name?: string;
  value?: unknown;
  onChange?: (...args: unknown[]) => void;
  onBlur?: (...args: unknown[]) => void;
  ref?: unknown;
}

export interface RHFFieldRenderProps {
  field: RHFFieldControl;
  fieldState: RHFFieldState;
}

export interface RHFFieldProps {
  name: string;
  label?: ReactNode;
  description?: ReactNode;
  required?: boolean;
  render: (props: RHFFieldRenderProps & { id: string; describedBy?: string; invalid?: boolean }) => ReactNode;
  field?: RHFFieldControl;
  fieldState?: RHFFieldState;
}

export function RHFField({
  label,
  description,
  required,
  render,
  field,
  fieldState,
}: RHFFieldProps) {
  const resolvedField: RHFFieldControl = field ?? {};
  const resolvedFieldState: RHFFieldState = fieldState ?? {};

  return (
    <FieldWrapper label={label} description={description} required={required} error={resolvedFieldState.error?.message}>
      {({ id, describedBy, invalid }) =>
        render({
          id,
          describedBy,
          invalid,
          field: resolvedField,
          fieldState: resolvedFieldState,
        })
      }
    </FieldWrapper>
  );
}
