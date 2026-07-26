import type { ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { useUploadStore } from '@/store/uploadStore';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const step = useUploadStore((s) => s.step);

  // After upload completes, UploadPage handles showing the DocumentCardSection.
  // No longer redirect to KnowledgeModelPage automatically.
  const isPostUpload = step === 'ready';

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Header />
        <main className="flex flex-1 flex-col items-center px-4 py-8 md:px-6">
          <div className={isPostUpload ? 'w-full max-w-4xl' : 'w-full max-w-2xl'}>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
