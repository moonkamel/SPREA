import { useEffect, useState } from 'react';

// Minimal client-side routing: Vercel serves index.html for every path.

const listeners = new Set<() => void>();

export function navigate(path: string) {
    if (path === window.location.pathname) return;
    window.history.pushState({}, '', path);
    window.scrollTo(0, 0);
    listeners.forEach(l => l());
}

export function usePath() {
    const [path, setPath] = useState(window.location.pathname);
    useEffect(() => {
        const update = () => setPath(window.location.pathname);
        listeners.add(update);
        window.addEventListener('popstate', update);
        return () => {
            listeners.delete(update);
            window.removeEventListener('popstate', update);
        };
    }, []);
    return path;
}

export function Link({ to, className = '', children }: { to: string; className?: string; children: React.ReactNode }) {
    return (
        <a
            href={to}
            className={className}
            onClick={e => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                e.preventDefault();
                navigate(to);
            }}
        >
            {children}
        </a>
    );
}
