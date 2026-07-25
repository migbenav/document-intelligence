import type { ReactNode } from 'react';
import { Header } from './Header';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <Header />
      <main className="flex flex-1 flex-col items-center px-4 py-8 md:px-6">
        <div className="w-full max-w-2xl">
          {children}
        </div>
      </main>
    </div>
  );
}
