import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

// A product screenshot in a browser-like frame; click to enlarge
export function Screen({ src, alt, width, height, eager = false, chrome = true }: {
    src: string;
    alt: string;
    width: number;
    height: number;
    eager?: boolean;
    chrome?: boolean;
}) {
    const [open, setOpen] = useState(false);
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open]);
    return (
        <>
            <button type="button" onClick={() => setOpen(true)} aria-label={`Agrandir : ${alt}`}
                className="block w-full text-left rounded-2xl border border-line bg-panel shadow-2xl shadow-black/50 overflow-hidden hover:border-brass/50 transition-colors cursor-zoom-in">
                {chrome && (
                    <span className="flex items-center gap-1.5 px-4 h-8 border-b border-line/80 bg-raised/60" aria-hidden="true">
                        <span className="h-2.5 w-2.5 rounded-full bg-line" /><span className="h-2.5 w-2.5 rounded-full bg-line" /><span className="h-2.5 w-2.5 rounded-full bg-line" />
                    </span>
                )}
                <img src={src} alt={alt} width={width} height={height} loading={eager ? 'eager' : 'lazy'} decoding="async" className="block w-full h-auto" />
            </button>
            {open && (
                <div className="fixed inset-0 z-[200] bg-black/85 backdrop-blur-sm flex items-center justify-center p-3 sm:p-8 cursor-zoom-out" onClick={() => setOpen(false)} role="dialog" aria-modal="true" aria-label={alt}>
                    <button className="absolute top-4 right-4 text-white/80 hover:text-white" aria-label="Fermer"><X size={28} /></button>
                    <img src={src} alt={alt} className="max-w-full max-h-full rounded-xl shadow-2xl" />
                </div>
            )}
        </>
    );
}
