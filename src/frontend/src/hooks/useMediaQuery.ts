import { useState, useEffect } from 'react';

/**
 * Hook that returns whether the given media query matches.
 * Updates reactively on viewport resize.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}
