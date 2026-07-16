export type ArrowDirection = "next" | "previous";

export interface RovingState {
  currentIndex: number;
  maxIndex: number;
  loop?: boolean;
}

export function getNextRovingIndex(state: RovingState, direction: ArrowDirection): number {
  const { currentIndex, maxIndex, loop = true } = state;
  if (direction === "next") {
    if (currentIndex >= maxIndex) {
      return loop ? 0 : maxIndex;
    }
    return currentIndex + 1;
  }

  if (currentIndex <= 0) {
    return loop ? maxIndex : 0;
  }
  return currentIndex - 1;
}

export function isActivationKey(key: string): boolean {
  return key === "Enter" || key === " ";
}

export function isHorizontalArrowKey(key: string): boolean {
  return key === "ArrowLeft" || key === "ArrowRight";
}

export function isVerticalArrowKey(key: string): boolean {
  return key === "ArrowUp" || key === "ArrowDown";
}
