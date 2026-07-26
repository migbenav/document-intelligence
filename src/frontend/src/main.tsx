import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { TranslationProvider } from './i18n';
import { usePreferencesStore } from './store/preferencesStore';
import './index.css';

function LocalizedApp() {
  const language = usePreferencesStore((state) => state.language);

  return (
    <TranslationProvider locale={language}>
      <App />
    </TranslationProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LocalizedApp />
  </React.StrictMode>,
);
