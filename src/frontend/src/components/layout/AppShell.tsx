import type { ReactNode } from 'react';
import { Header } from './Header';
import { useUploadStore } from '@/store/uploadStore';
import { KnowledgeModelPage } from '@/components/knowledge-model/KnowledgeModelPage';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const step = useUploadStore((s) => s.step);
  const documentId = useUploadStore((s) => s.documentId);

  const showKnowledgeModel = step === 'ready' && documentId !== null;

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <Header />
      <main className="flex flex-1 flex-col items-center px-4 py-8 md:px-6">
        {showKnowledgeModel ? (
          <div className="w-full max-w-6xl">
            <KnowledgeModelPage documentId={documentId} />
          </div>
        ) : (
          <div className="w-full max-w-2xl">
            {children}
          </div>
        )}
      </main>
    </div>
  );
}
