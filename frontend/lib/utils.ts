import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names safely.
 *
 * `clsx` resolves conditionals/arrays into a single string; `twMerge` then drops
 * earlier classes that conflict with later ones (e.g. "p-2 p-4" -> "p-4"), which
 * is what lets a caller override a component's default styling via `className`.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
