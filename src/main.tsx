import React from 'react'
import ReactDOM from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import App from './App.tsx'
import './index.css'

// Last resort: a rendering error shows a message instead of a blank page
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
    state = { failed: false };

    static getDerivedStateFromError() {
        return { failed: true };
    }

    componentDidCatch(error: unknown) {
        console.error(error);
    }

    render() {
        if (!this.state.failed) return this.props.children;
        return (
            <div role="alert" className="min-h-screen bg-canvas flex flex-col items-center justify-center gap-6 px-4 text-center">
                <p className="text-lg text-ink">Une erreur est survenue. Rechargez la page.</p>
                <button type="button" onClick={() => window.location.reload()}
                    className="inline-flex items-center justify-center rounded-xl px-5 h-12 font-semibold text-sm bg-brass text-canvas hover:bg-brass-light transition-colors">
                    Recharger la page
                </button>
            </div>
        );
    }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ErrorBoundary>
            <App />
                <Analytics />
        </ErrorBoundary>
    </React.StrictMode>,
)
