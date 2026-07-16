import type { ReactNode } from "react";

import { Dialog } from "../surface/Dialog";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  destructive?: boolean;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  return <Dialog {...props} />;
}
