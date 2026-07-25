import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Formats a byte count into a human-readable string (e.g., "1.5 MB").
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  if (bytes < 0) return '0 Bytes';

  const units = ['Bytes', 'KB', 'MB', 'GB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const unitIndex = Math.min(i, units.length - 1);
  const value = bytes / Math.pow(k, unitIndex);

  // Use up to 2 decimal places, but remove trailing zeros
  const formatted = value % 1 === 0 ? value.toString() : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return `${formatted} ${units[unitIndex]}`;
}
