/**
 * Table rows that open on click but ignore activation when the user is selecting text.
 */

import type { KeyboardEvent, MouseEvent, HTMLAttributes } from "react";

/** Pointer movement above this (px) counts as drag/select, not a row click. */
export const TABLE_ROW_DRAG_THRESHOLD_PX = 6;

type PointerPoint = { clientX: number; clientY: number };

const POINTER_DOWN_ATTR = "data-row-pointer-down";

function parsePointerDown(raw: string | undefined): PointerPoint | null {
  if (!raw) {
    return null;
  }
  const [x, y] = raw.split(",").map(Number);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  return { clientX: x, clientY: y };
}

export function hasActiveTextSelection(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    return false;
  }
  return sel.toString().trim().length > 0;
}

/** True when the current selection touches this row (more reliable than selection string alone). */
export function selectionIntersectsRow(row: Element): boolean {
  if (!hasActiveTextSelection()) {
    return false;
  }
  const sel = window.getSelection();
  if (!sel) {
    return false;
  }
  const nodes = [sel.anchorNode, sel.focusNode];
  for (const node of nodes) {
    if (!node) {
      continue;
    }
    const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as Element);
    if (el && row.contains(el)) {
      return true;
    }
  }
  return false;
}

export function pointerMovedBeyondDragThreshold(
  down: PointerPoint | null,
  up: { clientX: number; clientY: number },
  threshold = TABLE_ROW_DRAG_THRESHOLD_PX,
): boolean {
  if (!down) {
    return false;
  }
  return (
    Math.abs(up.clientX - down.clientX) > threshold ||
    Math.abs(up.clientY - down.clientY) > threshold
  );
}

export function isInteractiveTableTarget(
  target: EventTarget | null,
  extraSelector = "",
): boolean {
  if (!(target instanceof Element)) {
    return false;
  }
  const base = "button, a, select, textarea, input, label, summary, [data-row-action]";
  const selector = extraSelector ? `${base}, ${extraSelector}` : base;
  return Boolean(target.closest(selector));
}

export function shouldSuppressTableRowActivate(
  event: MouseEvent<HTMLTableRowElement>,
  extraInteractiveSelector = "",
): boolean {
  if (isInteractiveTableTarget(event.target, extraInteractiveSelector)) {
    return true;
  }
  const row = event.currentTarget;
  const pointerDown = parsePointerDown(row.getAttribute(POINTER_DOWN_ATTR) ?? undefined);
  if (pointerMovedBeyondDragThreshold(pointerDown, event)) {
    return true;
  }
  if (selectionIntersectsRow(row) || hasActiveTextSelection()) {
    return true;
  }
  return false;
}

export type SelectableTableRowOptions = {
  /** Extra selectors for cells that handle their own clicks (e.g. action columns). */
  extraInteractiveSelector?: string;
};

/**
 * Props for ``<tr>`` rows: click opens ``onActivate`` unless the user selected text or dragged.
 */
export function getSelectableTableRowProps(
  onActivate: () => void,
  options?: SelectableTableRowOptions,
): Pick<
  HTMLAttributes<HTMLTableRowElement>,
  "onMouseDown" | "onClick" | "onKeyDown" | "tabIndex" | "role"
> {
  const extra = options?.extraInteractiveSelector ?? "";

  return {
    role: "button",
    tabIndex: 0,
    onMouseDown: (event) => {
      if (event.button !== 0) {
        return;
      }
      const row = event.currentTarget;
      row.setAttribute(POINTER_DOWN_ATTR, `${event.clientX},${event.clientY}`);
    },
    onClick: (event) => {
      const row = event.currentTarget;
      try {
        if (shouldSuppressTableRowActivate(event, extra)) {
          return;
        }
        onActivate();
      } finally {
        row.removeAttribute(POINTER_DOWN_ATTR);
      }
    },
    onKeyDown: (event: KeyboardEvent<HTMLTableRowElement>) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      if (isInteractiveTableTarget(event.target, extra)) {
        return;
      }
      event.preventDefault();
      onActivate();
    },
  };
}
