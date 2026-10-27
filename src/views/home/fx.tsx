import { useEffect, useRef, useState, type ReactNode } from 'react';
import { animate, motion, useInView, useMotionValue, useReducedMotion, useSpring, useTransform } from 'framer-motion';

// Home page effects: kinetic title, counters, magnetic button, tilt cards.
// Everything falls back to a static rendering under prefers-reduced-motion.

/** WebGL scenes only where they can run smoothly: WebGL available, motion allowed. */
export function useCan3D() {
    const reduce = useReducedMotion();
    const [ok, setOk] = useState(false);
    useEffect(() => {
        if (reduce) return setOk(false);
        try {
            const c = document.createElement('canvas');
            setOk(!!(c.getContext('webgl2') || c.getContext('webgl')));
        } catch { setOk(false); }
    }, [reduce]);
    return ok;
}

/** Small screens or coarse pointers get the light version of the scenes. */
export function useLite() {
    const [lite, setLite] = useState(false);
    useEffect(() => {
        const mq = window.matchMedia('(max-width: 768px), (pointer: coarse)');
        const update = () => setLite(mq.matches);
        update();
        mq.addEventListener('change', update);
        return () => mq.removeEventListener('change', update);
    }, []);
    return lite;
}

/** True while the element is on screen: the scenes stop rendering off screen. */
export function useOnScreen<T extends Element>(margin = '120px') {
    const ref = useRef<T>(null);
    const [on, setOn] = useState(false);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { rootMargin: margin });
        io.observe(el);
        return () => io.disconnect();
    }, [margin]);
    return [ref, on] as const;
}

/** A line of text whose letters rise into place, word by word. */
export function KineticLine({ text, delay = 0, className = '' }: { text: string; delay?: number; className?: string }) {
    const reduce = useReducedMotion();
    if (reduce) return <span className={className}>{text}</span>;
    let i = 0;
    return (
        <span className={className} aria-label={text}>
            {text.split(' ').map((word, w) => (
                <span key={w} className="inline-block whitespace-nowrap" aria-hidden="true">
                    {[...word].map((ch, c) => (
                        <motion.span
                            key={c}
                            className="inline-block"
                            initial={{ y: '0.9em', opacity: 0, rotateX: -70, filter: 'blur(8px)' }}
                            animate={{ y: 0, opacity: 1, rotateX: 0, filter: 'blur(0px)' }}
                            transition={{ delay: delay + (i++) * 0.022, duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
                        >
                            {ch}
                        </motion.span>
                    ))}
                    {' '}
                </span>
            ))}
        </span>
    );
}

/** Words taking turns in the same slot. */
export function RotatingWord({ words, className = '' }: { words: string[]; className?: string }) {
    const reduce = useReducedMotion();
    const [i, setI] = useState(0);
    useEffect(() => {
        if (reduce) return;
        const t = setInterval(() => setI(n => (n + 1) % words.length), 2200);
        return () => clearInterval(t);
    }, [reduce, words.length]);
    return (
        <span className={`relative inline-grid align-baseline ${className}`}>
            {/* Reserve the width of the longest word */}
            {words.map(w => <span key={w} className="invisible col-start-1 row-start-1" aria-hidden="true">{w}</span>)}
            <span className="col-start-1 row-start-1 [clip-path:inset(0_-0.3em_-0.25em_-0.3em)]">
                <motion.span
                    key={words[i]}
                    className="inline-block"
                    initial={reduce ? false : { y: '100%', opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ duration: 0.55, ease: [0.2, 0.8, 0.2, 1] }}
                >
                    {words[i]}
                </motion.span>
            </span>
        </span>
    );
}

/** A number counting up when it scrolls into view. */
export function Counter({ to, decimals = 0, prefix = '', suffix = '', className = '' }: {
    to: number; decimals?: number; prefix?: string; suffix?: string; className?: string;
}) {
    const ref = useRef<HTMLSpanElement>(null);
    const inView = useInView(ref, { once: true, margin: '-15% 0px' });
    const reduce = useReducedMotion();
    const fmt = (v: number) => prefix + v.toLocaleString('fr-FR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
    useEffect(() => {
        const el = ref.current;
        if (!el || !inView) return;
        if (reduce) { el.textContent = fmt(to); return; }
        const c = animate(0, to, { duration: 1.8, ease: [0.16, 1, 0.3, 1], onUpdate: v => { el.textContent = fmt(v); } });
        return () => c.stop();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [inView, to, reduce]);
    return <span ref={ref} className={className}>{fmt(reduce ? to : 0)}</span>;
}

/** Fades and lifts its content in when it scrolls into view. */
export function Reveal({ children, delay = 0, className = '' }: { children: ReactNode; delay?: number; className?: string }) {
    return (
        <motion.div
            className={className}
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-10% 0px' }}
            transition={{ duration: 0.8, delay, ease: [0.2, 0.8, 0.2, 1] }}
        >
            {children}
        </motion.div>
    );
}

/** Button with a glow following the cursor (the button itself stays still). */
export function GlowButton({ children, onClick, variant = 'primary', className = '' }: {
    children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost'; className?: string;
}) {
    const ref = useRef<HTMLButtonElement>(null);
    const gx = useMotionValue(50), gy = useMotionValue(50);
    const glow = useTransform([gx, gy], ([a, b]) => `radial-gradient(circle at ${a}% ${b}%, rgba(255,236,190,0.55), transparent 60%)`);
    const ghostGlow = useTransform([gx, gy], ([a, b]) => `radial-gradient(circle at ${a}% ${b}%, rgba(227,201,143,0.18), transparent 65%)`);
    const move = (e: React.PointerEvent) => {
        const r = ref.current!.getBoundingClientRect();
        gx.set(((e.clientX - r.left) / r.width) * 100); gy.set(((e.clientY - r.top) / r.height) * 100);
    };
    const styles = variant === 'primary'
        ? 'bg-gradient-to-br from-brass-light via-brass to-brass-dark text-canvas shadow-[0_0_0_1px_rgba(227,201,143,0.4),0_8px_30px_-8px_rgba(201,164,92,0.65)] hover:shadow-[0_0_0_1px_rgba(227,201,143,0.75),0_0_48px_0_rgba(201,164,92,0.7)]'
        : 'border border-white/15 bg-white/[0.03] text-ink backdrop-blur hover:border-brass/60 hover:text-brass-light hover:shadow-[0_0_32px_-6px_rgba(201,164,92,0.45)]';
    return (
        <button ref={ref} type="button" onClick={onClick} onPointerMove={move}
            className={`group relative inline-flex items-center justify-center gap-2 rounded-full px-7 h-12 font-semibold text-sm transition-[box-shadow,border-color,color] duration-300 ${styles} ${className}`}>
            <motion.span aria-hidden="true" style={{ background: variant === 'primary' ? glow : ghostGlow }}
                className="absolute inset-0 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <span className="relative inline-flex items-center gap-2">{children}</span>
        </button>
    );
}

/** Card tilting in 3D under the cursor, with a light reflection. */
export function TiltCard({ children, className = '' }: { children: ReactNode; className?: string }) {
    const ref = useRef<HTMLDivElement>(null);
    const rx = useSpring(0, { stiffness: 160, damping: 18 });
    const ry = useSpring(0, { stiffness: 160, damping: 18 });
    // The reflection starts off the card: it only shows under the cursor
    const lx = useMotionValue(-100), ly = useMotionValue(-100);
    const shine = useTransform([lx, ly], ([a, b]) => `radial-gradient(600px circle at ${a}% ${b}%, rgba(227,201,143,0.16), transparent 45%)`);
    const move = (e: React.PointerEvent) => {
        if (e.pointerType !== 'mouse') return;
        const r = ref.current!.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
        ry.set((px - 0.5) * 14); rx.set((0.5 - py) * 10);
        lx.set(px * 100); ly.set(py * 100);
    };
    const leave = () => { rx.set(0); ry.set(0); lx.set(-100); ly.set(-100); };
    return (
        <motion.div ref={ref} onPointerMove={move} onPointerLeave={leave}
            style={{ rotateX: rx, rotateY: ry, transformPerspective: 1000 }}
            className={`relative ${className}`}>
            {children}
            <motion.div aria-hidden="true" style={{ background: shine }} className="pointer-events-none absolute inset-0 rounded-[inherit]" />
        </motion.div>
    );
}
