import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle } from 'lucide-react';
import { HELP, type HelpTopic } from './help';

// --- Formatting ---

export const eur = (n: number | null | undefined) =>
    `${Math.round(n || 0).toLocaleString('fr-FR')} €`;

export const num = (n: number | null | undefined) => Math.round(n || 0).toLocaleString('fr-FR');

// --- DPE labels (official 2021 colours) ---

export type DPEClass = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';
export const DPE_LABELS: DPEClass[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];

export const DPE_COLORS: Record<DPEClass, { bg: string; fg: string }> = {
    A: { bg: '#009C6D', fg: '#FFFFFF' },
    B: { bg: '#52B153', fg: '#FFFFFF' },
    C: { bg: '#78BD76', fg: '#0A0F1A' },
    D: { bg: '#F4E70F', fg: '#0A0F1A' },
    E: { bg: '#F0B40F', fg: '#0A0F1A' },
    F: { bg: '#EB8235', fg: '#0A0F1A' },
    G: { bg: '#D7221F', fg: '#FFFFFF' },
};

export function DpeBadge({ label, size = 'md' }: { label?: DPEClass | null; size?: 'sm' | 'md' | 'lg' }) {
    const dims = { sm: 'h-7 w-7 text-sm rounded-md', md: 'h-10 w-10 text-lg rounded-lg', lg: 'h-14 w-14 text-2xl rounded-xl' }[size];
    if (!label) return <span className={`${dims} inline-flex items-center justify-center bg-raised text-faint`}>–</span>;
    const c = DPE_COLORS[label];
    return (
        <span className={`${dims} inline-flex shrink-0 items-center justify-center font-sans font-bold`} style={{ backgroundColor: c.bg, color: c.fg }} aria-label={`Classe ${label}`}>
            {label}
        </span>
    );
}

// Classic DPE ladder with "today" and "after works" markers
export function DpeScale({ thresholds, current, target }: {
    thresholds: { label: DPEClass; max: number }[];
    current?: DPEClass;
    target?: DPEClass;
}) {
    return (
        <div className="space-y-1.5" role="list" aria-label="Échelle DPE">
            {thresholds.map((t, i) => {
                const c = DPE_COLORS[t.label];
                const isCurrent = t.label === current;
                const isTarget = t.label === target;
                const prev = i > 0 ? thresholds[i - 1].max : null;
                const range = i === 0 ? `≤ ${t.max}` : i === thresholds.length - 1 ? `> ${prev}` : `${(prev ?? 0) + 1} à ${t.max}`;
                return (
                    <div key={t.label} role="listitem" className="flex items-center gap-3">
                        <div
                            className={`h-8 flex items-center justify-between px-3 rounded-r-md font-bold transition-all ${isCurrent || isTarget ? 'ring-2 ring-ink ring-offset-2 ring-offset-panel' : ''}`}
                            style={{ width: `${34 + i * 9}%`, backgroundColor: c.bg, color: c.fg }}
                        >
                            <span>{t.label}</span>
                            <span className="text-[11px] font-medium opacity-80 hidden sm:inline">{range}</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5 text-xs">
                            {isCurrent && <span className="px-2 py-0.5 rounded-full border border-line text-ink-soft">Aujourd'hui</span>}
                            {isTarget && <span className="px-2 py-0.5 rounded-full bg-brass text-canvas font-semibold">Après travaux</span>}
                        </div>
                    </div>
                );
            })}
            <p className="text-xs text-faint pt-1">Consommation en kWh/m²/an d'énergie primaire.</p>
        </div>
    );
}

// --- Help bubble ---

export function Help({ topic, title, text, className = '' }: { topic?: HelpTopic; title?: string; text?: string; className?: string }) {
    const content = topic ? HELP[topic] : { title: title || '', text: text || '' };
    const [open, setOpen] = useState(false);
    const [pos, setPos] = useState<{ top: number; left: number; above: boolean } | null>(null);
    const button = useRef<HTMLButtonElement>(null);
    const popover = useRef<HTMLDivElement>(null);
    const hoverTimer = useRef<number>();

    useLayoutEffect(() => {
        if (!open || !button.current) return;
        const r = button.current.getBoundingClientRect();
        const width = Math.min(300, window.innerWidth - 24);
        const left = Math.min(Math.max(12, r.left + r.width / 2 - width / 2), window.innerWidth - width - 12);
        const above = r.bottom + 180 > window.innerHeight && r.top > 200;
        setPos({ top: above ? r.top - 8 : r.bottom + 8, left, above });
    }, [open]);

    useEffect(() => {
        if (!open) return;
        const close = (e: Event) => {
            if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
            if (e.type === 'mousedown' && (button.current?.contains(e.target as Node) || popover.current?.contains(e.target as Node))) return;
            setOpen(false);
        };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', close);
        window.addEventListener('scroll', close, true);
        window.addEventListener('resize', close);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', close);
            window.removeEventListener('scroll', close, true);
            window.removeEventListener('resize', close);
        };
    }, [open]);

    const hover = (state: boolean) => {
        window.clearTimeout(hoverTimer.current);
        hoverTimer.current = window.setTimeout(() => setOpen(state), state ? 120 : 200);
    };

    return (
        <>
            <button
                ref={button}
                type="button"
                aria-label={`Aide : ${content.title}`}
                aria-expanded={open}
                onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
                onMouseEnter={() => hover(true)}
                onMouseLeave={() => hover(false)}
                className={`inline-flex align-middle text-faint hover:text-brass transition-colors ${className}`}
            >
                <HelpCircle size={15} />
            </button>
            {open && pos && createPortal(
                <div
                    ref={popover}
                    role="tooltip"
                    onMouseEnter={() => hover(true)}
                    onMouseLeave={() => hover(false)}
                    className="fixed z-[200] w-[300px] max-w-[calc(100vw-24px)] rounded-xl border border-line bg-raised p-4 shadow-2xl shadow-black/50 text-left"
                    style={{ left: pos.left, top: pos.top, transform: pos.above ? 'translateY(-100%)' : undefined }}
                >
                    <p className="font-semibold text-ink text-sm mb-1">{content.title}</p>
                    <p className="text-[13px] leading-relaxed text-ink-soft">{content.text}</p>
                </div>,
                document.body,
            )}
        </>
    );
}

// --- Layout ---

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
    return <div className={`rounded-2xl border border-line bg-panel ${className}`}>{children}</div>;
}

export function Step({ n, title, subtitle, help, aside, children }: {
    n: number;
    title: string;
    subtitle?: string;
    help?: HelpTopic;
    aside?: ReactNode;
    children: ReactNode;
}) {
    return (
        <Card className="p-5 sm:p-7">
            <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
                <div className="flex items-start gap-4">
                    <span className="mt-0.5 h-8 w-8 shrink-0 rounded-full border border-brass/50 text-brass font-serif text-base flex items-center justify-center">{n}</span>
                    <div>
                        <h2 className="text-xl sm:text-2xl text-ink flex items-center gap-2">{title}{help && <Help topic={help} />}</h2>
                        {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
                    </div>
                </div>
                {aside}
            </header>
            {children}
        </Card>
    );
}

export function Label({ children, help }: { children: ReactNode; help?: HelpTopic }) {
    return <span className="text-sm text-ink-soft font-medium flex items-center gap-1.5">{children}{help && <Help topic={help} />}</span>;
}

// --- Controls ---

export function Button({ children, onClick, variant = 'primary', disabled, className = '', type = 'button' }: {
    children: ReactNode;
    onClick?: () => void;
    variant?: 'primary' | 'secondary' | 'ghost';
    disabled?: boolean;
    className?: string;
    type?: 'button' | 'submit';
}) {
    const styles = {
        primary: 'bg-brass text-canvas hover:bg-brass-light disabled:bg-raised disabled:text-faint',
        secondary: 'border border-line text-ink hover:border-brass/60 hover:text-brass-light disabled:text-faint',
        ghost: 'text-muted hover:text-ink',
    }[variant];
    return (
        <button type={type} onClick={onClick} disabled={disabled}
            className={`inline-flex items-center justify-center gap-2 rounded-xl px-5 h-12 font-semibold text-sm transition-colors disabled:cursor-not-allowed ${styles} ${className}`}>
            {children}
        </button>
    );
}

export function Segmented<T extends string>({ value, options, onChange, ariaLabel }: {
    value: T;
    options: { value: T; label: ReactNode; hint?: string }[];
    onChange: (v: T) => void;
    ariaLabel: string;
}) {
    return (
        <div role="radiogroup" aria-label={ariaLabel} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
            {options.map(o => (
                <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
                    className={`rounded-xl border px-3 py-2.5 text-sm text-left transition-colors ${value === o.value ? 'border-brass bg-brass/10 text-ink' : 'border-line text-muted hover:text-ink hover:border-faint'}`}>
                    <span className="font-medium block">{o.label}</span>
                    {o.hint && <span className="block text-xs text-faint mt-0.5">{o.hint}</span>}
                </button>
            ))}
        </div>
    );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
    return (
        <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? 'bg-brass' : 'bg-line'}`}>
            <span className={`absolute top-1 h-4 w-4 rounded-full bg-ink transition-all ${checked ? 'left-6' : 'left-1'}`} />
        </button>
    );
}

export function NumberField({ value, onChange, suffix, min = 0, step, ariaLabel }: {
    value: number | '';
    onChange: (v: number | '') => void;
    suffix?: string;
    min?: number;
    step?: number;
    ariaLabel: string;
}) {
    return (
        <div className="flex items-center rounded-xl border border-line bg-raised focus-within:border-brass/70 transition-colors">
            <input
                type="number" inputMode="decimal" min={min} step={step} aria-label={ariaLabel}
                value={value}
                onChange={e => onChange(e.target.value === '' ? '' : Math.max(min, Number(e.target.value)))}
                className="w-full min-w-0 bg-transparent px-3.5 h-11 text-ink outline-none"
            />
            {suffix && <span className="pr-3.5 text-sm text-faint whitespace-nowrap">{suffix}</span>}
        </div>
    );
}

export function Row({ label, help, value, tone, strong }: {
    label: ReactNode;
    help?: HelpTopic;
    value: ReactNode;
    tone?: 'positive' | 'muted';
    strong?: boolean;
}) {
    const color = tone === 'positive' ? 'text-sage' : tone === 'muted' ? 'text-muted' : 'text-ink';
    return (
        <div className={`flex items-baseline justify-between gap-4 py-2 ${strong ? 'font-semibold' : ''}`}>
            <span className="text-sm text-ink-soft flex items-center gap-1.5">{label}{help && <Help topic={help} />}</span>
            <span className={`tabular-nums text-right ${color}`}>{value}</span>
        </div>
    );
}
