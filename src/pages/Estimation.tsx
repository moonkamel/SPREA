import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { animate, AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowRight, Building2, Check, ChevronDown, Home as HomeIcon, Loader2, MapPin, Search, ShieldCheck, Sparkles, TrendingDown, TrendingUp, Wand2 } from 'lucide-react';
import { SiteFooter, SiteHeader } from './site';
import { useSeo } from '../seo';
import { DPE_COLORS, DPE_LABELS, errorDetail, type DPEClass } from '../ui';
import { GlowButton, Reveal } from '../views/home/fx';
import faqData from '../data/estimation_faq.json';

// Public online estimator: address, a few taps (prefilled from the DPE of the
// address, or from a sentence read by the AI), a live estimate from the DVF
// sales around, then the owner can ask a local advisor to call them back.

type Kind = 'appartement' | 'maison';
type Condition = 'a_renover' | 'rafraichir' | 'bon' | 'refait';
type Outdoor = 'balcon' | 'terrasse' | 'jardin';

interface Place { label: string; insee: string; postcode: string; city: string; lat: number; lon: number }
interface Form {
    kind: Kind; surface: number | ''; rooms: number | null; land: number | ''; floor: number | null;
    elevator: boolean | null; outdoor: Outdoor[]; parking: boolean; pool: boolean; condition: Condition; dpe: DPEClass | null;
}
interface Dpe { kind: Kind; surface: number; dpe: DPEClass | null; year: number | null; date: string | null }
interface Result {
    value: number; low: number; high: number; price_m2: number; market_m2: number; dpe_effect: number | null;
    adjustments: { label: string; pct: number }[]; adjustment_total: number;
    reliability: { score: number; label: string }; trend: { pct: number; from: string; to: string } | null;
    renovation: { target: string; gain: number } | null; sales: number; scope: string; period: string;
    comparables: { date: string; street: string; commune?: string; surface: number; rooms?: number; price: number; adjusted_m2: number; distance: number | null }[];
}

const EMPTY: Form = { kind: 'appartement', surface: '', rooms: null, land: '', floor: null, elevator: null, outdoor: [], parking: false, pool: false, condition: 'bon', dpe: null };
const CONDITIONS: [Condition, string][] = [['a_renover', 'À rénover'], ['rafraichir', 'À rafraîchir'], ['bon', 'Bon état'], ['refait', 'Refait à neuf']];
const PROJECTS: [string, string][] = [['vendre_3m', 'Vendre sous 3 mois'], ['vendre_12m', "Vendre dans l'année"], ['reflexion', 'En réflexion'], ['curiosite', 'Simple curiosité']];
const CONSENT = "J'accepte d'être recontacté(e) par téléphone ou par email au sujet de mon projet par un conseiller immobilier partenaire de SPREA exerçant dans mon secteur, à qui mes coordonnées et les informations de mon estimation sont transmises. Je peux retirer ce consentement à tout moment.";

const euro = (n: number) => `${Math.round(n).toLocaleString('fr-FR')} €`;
const quarter = (q: string) => (/^\d{4}T\d$/.test(q) ? `${['1er', '2e', '3e', '4e'][+q[5] - 1]} trim. ${q.slice(0, 4)}` : q);

export default function EstimationPage() {
    useSeo({
        title: 'Estimation immobilière gratuite en ligne, immédiate et sans inscription | SPREA',
        description: "Estimez gratuitement votre maison ou votre appartement en 30 secondes : prix calculé sur les ventes réelles autour de chez vous (DVF), ajusté de l'étiquette énergie. Sans inscription.",
        path: '/estimation',
    });
    const [place, setPlace] = useState<Place | null>(null);
    const [form, setForm] = useState<Form>(EMPTY);
    const [dpes, setDpes] = useState<Dpe[] | null>(null);
    const [touched, setTouched] = useState<Set<string>>(new Set());
    const [result, setResult] = useState<Result | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const formRef = useRef<HTMLDivElement>(null);
    // On small screens the result sits under the form: a bar shows it while the form is filled
    const resultRef = useRef<HTMLDivElement>(null);
    const [resultSeen, setResultSeen] = useState(false);
    useEffect(() => {
        const el = resultRef.current;
        if (!el) return;
        const io = new IntersectionObserver(([e]) => setResultSeen(e.isIntersecting), { rootMargin: '0px 0px -30% 0px' });
        io.observe(el);
        return () => io.disconnect();
    }, [place]);

    const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm(f => ({ ...f, [k]: v }));
    // Fields filled by the DPE or the AI flash briefly
    const flash = (keys: string[]) => { setTouched(new Set(keys)); setTimeout(() => setTouched(new Set()), 1600); };
    const apply = (fields: Partial<Form>) => { setForm(f => ({ ...f, ...fields })); flash(Object.keys(fields)); };

    // DPE published at the address: prefill (one) or let the owner pick (several)
    useEffect(() => {
        if (!place) return;
        setDpes(null);
        let stop = false;
        fetch(`/api/estimate/dpe?q=${encodeURIComponent(place.label)}`).then(r => r.ok ? r.json() : { results: [] }).then(d => {
            if (stop) return;
            const list: Dpe[] = d.results || [];
            setDpes(list);
            if (list.length === 1) applyDpe(list[0]);
        }).catch(() => !stop && setDpes([]));
        return () => { stop = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [place]);
    const applyDpe = (d: Dpe) => apply({ kind: d.kind, surface: d.surface, ...(d.dpe ? { dpe: d.dpe } : {}) });

    // Live estimate, debounced
    const ready = !!place && typeof form.surface === 'number' && form.surface >= 9;
    const payload = useMemo(() => place && ready ? {
        address: place.label, insee: place.insee, postcode: place.postcode, city: place.city, lat: place.lat, lon: place.lon,
        kind: form.kind, surface: form.surface, rooms: form.rooms, land: form.kind === 'maison' && form.land !== '' ? form.land : null,
        floor: form.kind === 'appartement' ? form.floor : null, elevator: form.kind === 'appartement' ? form.elevator : null,
        outdoor: form.outdoor, parking: form.parking, pool: form.kind === 'maison' && form.pool, condition: form.condition, dpe: form.dpe,
    } : null, [place, form, ready]);
    useEffect(() => {
        if (!payload) return;
        const ctl = new AbortController();
        setBusy(true);
        const t = setTimeout(async () => {
            try {
                const res = await fetch('/api/estimate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: ctl.signal });
                if (!res.ok) { setError(await errorDetail(res, "L'estimation n'a pas pu être calculée.")); setResult(null); }
                else { setResult(await res.json()); setError(null); }
            } catch (e) { if ((e as Error).name !== 'AbortError') setError("L'estimation n'a pas pu être calculée."); }
            finally { if (!ctl.signal.aborted) setBusy(false); }
        }, 350);
        return () => { clearTimeout(t); ctl.abort(); };
    }, [payload]);

    const pick = (p: Place) => {
        setPlace(p); setForm(EMPTY); setResult(null); setError(null);
        setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
    };

    return (
        <div className="min-h-screen flex flex-col bg-canvas overflow-x-clip">
            <SiteHeader />
            <main className="flex-1">
                <section className="relative overflow-hidden">
                    <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_50%_60%_at_80%_20%,rgba(40,120,255,0.18),transparent_70%),radial-gradient(ellipse_50%_50%_at_10%_10%,rgba(201,164,92,0.12),transparent_70%)]" />
                    <div aria-hidden="true" className="absolute inset-0 opacity-[0.06] bg-[linear-gradient(rgba(255,255,255,0.6)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.6)_1px,transparent_1px)] bg-[size:64px_64px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_75%)]" />
                    <div className="relative max-w-3xl mx-auto px-4 sm:px-6 pt-12 sm:pt-16 pb-10 text-center">
                        <p className="inline-flex items-center gap-2 rounded-full border border-brass/30 bg-brass/[0.06] px-4 py-1.5 text-xs sm:text-sm text-brass-light">
                            <span className="h-1.5 w-1.5 rounded-full bg-brass-light animate-pulse" /> Estimation immobilière gratuite · sans inscription
                        </p>
                        <h1 className="mt-5 text-[2rem] sm:text-5xl leading-[1.08] text-ink">Combien vaut votre bien&nbsp;? <span className="block text-brass-light">Réponse en 30 secondes.</span></h1>
                        <p className="mt-4 text-[15px] sm:text-base text-ink-soft/90 max-w-xl mx-auto">
                            Un prix calculé sur les ventes réelles autour de chez vous, ajusté de l'étiquette énergie mesurée sur plus d'un million de ventes. Immédiat, gratuit, sans email à donner.
                        </p>
                        <div className="mt-8 text-left"><AddressSearch onPick={pick} picked={place} /></div>
                        <p className="mt-4 text-xs text-faint flex items-center justify-center gap-2"><ShieldCheck size={14} className="text-sage" /> Ventes DVF de la DGFiP · DPE de l'ADEME · aucune donnée revendue</p>
                    </div>
                </section>

                <AnimatePresence>
                    {place && (
                        <motion.section ref={formRef} initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                            className="max-w-6xl mx-auto px-4 sm:px-6 pb-16 scroll-mt-20">
                            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] items-start">
                                <div className="space-y-4">
                                    <AiDescribe onFields={apply} />
                                    {dpes && dpes.length > 1 && (
                                        <Panel title="Nous avons trouvé plusieurs DPE à cette adresse" subtitle="Lequel est votre logement ? Les champs se remplissent tout seuls.">
                                            <div className="flex flex-wrap gap-2">
                                                {dpes.map((d, i) => (
                                                    <button key={i} type="button" onClick={() => applyDpe(d)}
                                                        className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-raised/60 px-3 py-2 text-sm text-ink-soft hover:border-brass/50 hover:text-ink transition-colors">
                                                        {d.dpe && <span className="h-5 w-5 rounded text-[11px] font-bold inline-flex items-center justify-center" style={{ background: DPE_COLORS[d.dpe].bg, color: DPE_COLORS[d.dpe].fg }}>{d.dpe}</span>}
                                                        {d.kind === 'maison' ? 'Maison' : 'Appartement'} · {d.surface} m²{d.year ? ` · ${d.year}` : ''}
                                                    </button>
                                                ))}
                                            </div>
                                        </Panel>
                                    )}
                                    {dpes && dpes.length === 1 && (
                                        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-sage">
                                            <Check size={16} /> DPE trouvé à cette adresse : {dpes[0].kind === 'maison' ? 'maison' : 'appartement'} de {dpes[0].surface} m²{dpes[0].dpe ? `, classe ${dpes[0].dpe}` : ''}.
                                            <span className="text-muted">Pas votre logement ? Corrigez les champs ci-dessous.</span>
                                        </p>
                                    )}
                                    <Panel title="Votre bien">
                                        <Field label="Type">
                                            <Chips value={form.kind} onChange={v => set('kind', v)} flash={touched.has('kind')}
                                                options={[['appartement', <><Building2 size={16} /> Appartement</>], ['maison', <><HomeIcon size={16} /> Maison</>]]} />
                                        </Field>
                                        <Field label="Surface habitable">
                                            <Surface value={form.surface} onChange={v => set('surface', v)} flash={touched.has('surface')} />
                                        </Field>
                                        <Field label="Pièces">
                                            <Chips value={form.rooms} onChange={v => set('rooms', v)} flash={touched.has('rooms')}
                                                options={[1, 2, 3, 4, 5, 6].map(n => [n, n === 6 ? '6+' : String(n)] as [number, string])} />
                                        </Field>
                                        {form.kind === 'appartement' ? (
                                            <>
                                                <Field label="Étage">
                                                    <Chips value={form.floor} onChange={v => set('floor', v)} flash={touched.has('floor')}
                                                        options={[0, 1, 2, 3, 4, 5].map(n => [n, n === 0 ? 'RDC' : n === 5 ? '5+' : String(n)] as [number, string])} />
                                                </Field>
                                                {form.floor !== null && form.floor > 0 && (
                                                    <Field label="Ascenseur">
                                                        <Chips value={form.elevator} onChange={v => set('elevator', v)} flash={touched.has('elevator')} options={[[true, 'Oui'], [false, 'Non']]} />
                                                    </Field>
                                                )}
                                            </>
                                        ) : (
                                            <Field label="Terrain">
                                                <div className="flex items-center gap-2">
                                                    <input inputMode="numeric" value={form.land} placeholder="Optionnel"
                                                        onChange={e => set('land', e.target.value === '' ? '' : Math.max(0, Math.min(100000, +e.target.value.replace(/\D/g, ''))))}
                                                        className={`w-32 h-11 rounded-xl border bg-raised px-3 text-ink outline-none focus:border-brass/70 ${touched.has('land') ? 'border-brass ring-2 ring-brass/40' : 'border-line'}`} />
                                                    <span className="text-sm text-muted">m²</span>
                                                </div>
                                            </Field>
                                        )}
                                        <Field label="Atouts">
                                            <div className="flex flex-wrap gap-2">
                                                {(['balcon', 'terrasse', 'jardin'] as Outdoor[]).filter(o => !(o === 'jardin' && form.kind === 'maison')).map(o => (
                                                    <Toggle key={o} on={form.outdoor.includes(o)} flash={touched.has('outdoor')}
                                                        onClick={() => set('outdoor', form.outdoor.includes(o) ? form.outdoor.filter(x => x !== o) : [...form.outdoor, o])}>
                                                        {o[0].toUpperCase() + o.slice(1)}
                                                    </Toggle>
                                                ))}
                                                <Toggle on={form.parking} flash={touched.has('parking')} onClick={() => set('parking', !form.parking)}>Parking / garage</Toggle>
                                                {form.kind === 'maison' && <Toggle on={form.pool} flash={touched.has('pool')} onClick={() => set('pool', !form.pool)}>Piscine</Toggle>}
                                            </div>
                                        </Field>
                                        <Field label="État">
                                            <Chips value={form.condition} onChange={v => set('condition', v)} flash={touched.has('condition')} options={CONDITIONS} />
                                        </Field>
                                        <Field label="Étiquette énergie (DPE)">
                                            <div className="flex flex-wrap items-center gap-1.5">
                                                {DPE_LABELS.map(l => (
                                                    <button key={l} type="button" onClick={() => set('dpe', form.dpe === l ? null : l)} aria-pressed={form.dpe === l}
                                                        className={`h-10 w-10 rounded-lg font-bold transition-all ${form.dpe === l ? 'scale-110 ring-2 ring-white/80' : 'opacity-60 hover:opacity-100'} ${touched.has('dpe') && form.dpe === l ? 'ring-brass' : ''}`}
                                                        style={{ background: DPE_COLORS[l].bg, color: DPE_COLORS[l].fg }}>{l}</button>
                                                ))}
                                                <button type="button" onClick={() => set('dpe', null)} className={`ml-1 h-10 px-3 rounded-lg text-sm border transition-colors ${form.dpe === null ? 'border-brass/60 text-brass-light' : 'border-line text-muted hover:text-ink'}`}>Je ne sais pas</button>
                                            </div>
                                        </Field>
                                    </Panel>
                                </div>
                                <div id="resultat" ref={resultRef} className="lg:sticky lg:top-20 scroll-mt-20">
                                    <ResultCard result={result} busy={busy} error={error} ready={ready} place={place} form={form} payload={payload} />
                                </div>
                            </div>
                        </motion.section>
                    )}
                </AnimatePresence>

                <AnimatePresence>
                    {result && !resultSeen && (
                        <motion.button type="button" initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }}
                            onClick={() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                            className="lg:hidden fixed bottom-3 inset-x-3 z-40 flex items-center justify-between gap-3 rounded-2xl border border-brass/40 bg-panel/95 backdrop-blur px-4 h-14 shadow-[0_10px_40px_rgba(0,0,0,0.6)]">
                            <span className="text-left"><span className="block text-[10px] uppercase tracking-[0.16em] text-brass">Votre estimation</span><span className="font-serif text-xl text-ink tabular-nums">{euro(result.value)}</span></span>
                            <span className="inline-flex items-center gap-1 text-sm text-brass-light">Voir le détail <ChevronDown size={16} /></span>
                        </motion.button>
                    )}
                </AnimatePresence>

                <SeoContent />
            </main>
            <SiteFooter />
        </div>
    );
}

// --- Address with the Base Adresse Nationale autocomplete ---

function AddressSearch({ onPick, picked }: { onPick: (p: Place) => void; picked: Place | null }) {
    // From a « Prix m² à <commune> » page: the commune is typed, the owner adds the street
    const [q, setQ] = useState(() => { const c = new URLSearchParams(window.location.search).get('commune'); return c ? `${c.slice(0, 60)} ` : ''; });
    const [list, setList] = useState<Place[]>([]);
    const [active, setActive] = useState(0);
    const [chosen, setChosen] = useState('');
    useEffect(() => {
        if (q.length < 3 || q === chosen) { setList([]); return; }
        const ctl = new AbortController();
        const t = setTimeout(async () => {
            try {
                const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&limit=6&autocomplete=1`, { signal: ctl.signal });
                const d = await res.json();
                setList((d.features || []).map((f: any) => ({
                    label: f.properties.label, insee: f.properties.citycode, postcode: f.properties.postcode, city: f.properties.city,
                    lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0],
                })));
                setActive(0);
            } catch { /* typing on */ }
        }, 180);
        return () => { clearTimeout(t); ctl.abort(); };
    }, [q, chosen]);
    const choose = (p: Place) => { setChosen(p.label); setQ(p.label); setList([]); onPick(p); };
    return (
        <div className="relative">
            <form onSubmit={e => { e.preventDefault(); if (list[active]) choose(list[active]); }}
                className="flex items-center gap-3 rounded-2xl border border-white/15 bg-panel/80 backdrop-blur px-4 h-16 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)] focus-within:border-brass/70 focus-within:shadow-[0_0_0_4px_rgba(201,164,92,0.15)] transition-all">
                <Search size={20} className="text-brass shrink-0" />
                <input autoFocus onFocus={e => e.currentTarget.setSelectionRange(0, 0)} aria-label="Adresse du bien" placeholder="Adresse du bien : 12 rue de la Paix, Lille" value={q}
                    onChange={e => setQ(e.target.value)}
                    onKeyDown={e => {
                        if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, list.length - 1)); }
                        if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
                    }}
                    className="flex-1 min-w-0 bg-transparent text-base sm:text-lg text-ink placeholder:text-faint outline-none" />
                {picked && picked.label === q ? <Check size={20} className="text-sage shrink-0" /> : (
                    <button type="submit" disabled={!list.length} className="hidden sm:inline-flex items-center gap-1.5 rounded-xl bg-brass text-canvas font-semibold text-sm px-4 h-10 disabled:opacity-40 hover:bg-brass-light transition-colors">
                        Estimer <ArrowRight size={16} />
                    </button>
                )}
            </form>
            {list.length > 0 && (
                <ul className="absolute left-0 right-0 top-full mt-2 z-30 rounded-2xl border border-white/10 bg-panel shadow-2xl shadow-black/60 overflow-hidden" role="listbox">
                    {list.map((p, i) => (
                        <li key={p.label} role="option" aria-selected={i === active}>
                            <button type="button" onMouseEnter={() => setActive(i)} onClick={() => choose(p)}
                                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${i === active ? 'bg-raised text-ink' : 'text-ink-soft'}`}>
                                <MapPin size={16} className="text-brass shrink-0" /> {p.label}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

// --- A sentence read by the AI ---

function AiDescribe({ onFields }: { onFields: (f: Partial<Form>) => void }) {
    const [open, setOpen] = useState(false);
    const [text, setText] = useState('');
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState<number | null>(null);
    const run = async () => {
        if (text.trim().length < 3) return;
        setBusy(true); setDone(null);
        try {
            const res = await fetch('/api/estimate/parse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
            if (res.ok) {
                const f = (await res.json()).fields || {};
                const out: Partial<Form> = {};
                if (f.kind) out.kind = f.kind;
                if (f.surface) out.surface = Math.round(f.surface);
                if (f.rooms) out.rooms = Math.min(6, f.rooms);
                if (f.land) out.land = Math.round(f.land);
                if (f.floor !== undefined) out.floor = Math.min(5, f.floor);
                if (f.elevator !== undefined) out.elevator = f.elevator;
                if (f.outdoor?.length) out.outdoor = f.outdoor;
                if (f.parking) out.parking = true;
                if (f.pool) out.pool = true;
                if (f.condition) out.condition = f.condition;
                if (f.dpe) out.dpe = f.dpe;
                onFields(out);
                setDone(Object.keys(out).length);
            }
        } finally { setBusy(false); }
    };
    return (
        <div className="rounded-2xl border border-brass/25 bg-gradient-to-br from-brass/[0.08] to-transparent p-4">
            <button type="button" onClick={() => setOpen(o => !o)} className="w-full flex items-center justify-between gap-3 text-left">
                <span className="flex items-center gap-2.5 text-sm text-ink"><Sparkles size={18} className="text-brass-light" /> <span><b className="font-semibold">Plus rapide :</b> décrivez votre bien en une phrase, l'IA remplit tout</span></span>
                <ChevronDown size={18} className={`text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence initial={false}>
                {open && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                        <textarea value={text} onChange={e => setText(e.target.value)} rows={3} maxLength={1500}
                            placeholder="Ex. : T3 de 68 m² au 4e avec ascenseur, balcon, cave et parking, refait à neuf, DPE C. Ou collez le texte de votre annonce."
                            className="mt-3 w-full rounded-xl border border-line bg-raised px-3 py-2.5 text-sm text-ink placeholder:text-faint outline-none focus:border-brass/70 resize-none" />
                        <div className="mt-2 flex items-center gap-3">
                            <button type="button" onClick={run} disabled={busy || text.trim().length < 3}
                                className="inline-flex items-center gap-2 rounded-xl bg-brass text-canvas text-sm font-semibold px-4 h-10 disabled:opacity-40 hover:bg-brass-light transition-colors">
                                {busy ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />} Remplir pour moi
                            </button>
                            {done !== null && <span className="text-sm text-sage">{done ? `${done} champ${done > 1 ? 's' : ''} rempli${done > 1 ? 's' : ''}` : 'Rien de reconnu, complétez ci-dessous'}</span>}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

// --- Form building blocks ---

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
    return (
        <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6">
            <h2 className="text-lg text-ink">{title}</h2>
            {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
            <div className="mt-4 space-y-5">{children}</div>
        </div>
    );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
    return <div><p className="mb-2 text-xs uppercase tracking-[0.14em] text-faint">{label}</p>{children}</div>;
}

function Chips<T extends string | number | boolean | null>({ value, onChange, options, flash }: {
    value: T; onChange: (v: T) => void; options: [T, ReactNode][]; flash?: boolean;
}) {
    return (
        <div className="flex flex-wrap gap-2">
            {options.map(([v, label]) => {
                const on = v === value;
                return (
                    <button key={String(v)} type="button" onClick={() => onChange(v)} aria-pressed={on}
                        className={`inline-flex items-center gap-2 rounded-xl border px-3.5 h-10 text-sm transition-all ${on
                            ? `border-brass bg-brass/15 text-brass-light ${flash ? 'ring-2 ring-brass/50' : ''}` : 'border-line text-ink-soft hover:border-white/30 hover:text-ink'}`}>
                        {label}
                    </button>
                );
            })}
        </div>
    );
}

function Toggle({ on, onClick, children, flash }: { on: boolean; onClick: () => void; children: ReactNode; flash?: boolean }) {
    return (
        <button type="button" onClick={onClick} aria-pressed={on}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3.5 h-10 text-sm transition-all ${on ? `border-brass bg-brass/15 text-brass-light ${flash ? 'ring-2 ring-brass/50' : ''}` : 'border-line text-ink-soft hover:border-white/30 hover:text-ink'}`}>
            {on && <Check size={14} />}{children}
        </button>
    );
}

function Surface({ value, onChange, flash }: { value: number | ''; onChange: (v: number | '') => void; flash?: boolean }) {
    const v = value === '' ? 60 : value;
    return (
        <div className="flex items-center gap-4">
            <div className={`flex items-center gap-2 rounded-xl border bg-raised px-3 h-12 w-32 ${flash ? 'border-brass ring-2 ring-brass/40' : 'border-line focus-within:border-brass/70'}`}>
                <input inputMode="numeric" aria-label="Surface en m²" value={value} placeholder="65"
                    onChange={e => { const n = e.target.value.replace(/\D/g, ''); onChange(n === '' ? '' : Math.min(1000, +n)); }}
                    className="w-full bg-transparent text-lg text-ink outline-none" />
                <span className="text-muted">m²</span>
            </div>
            <input type="range" min={10} max={300} step={1} value={Math.min(300, v)} onChange={e => onChange(+e.target.value)} aria-label="Surface"
                className="flex-1 accent-[#C9A45C]" />
        </div>
    );
}

// --- Result ---

function AnimatedEuro({ value, className = '' }: { value: number; className?: string }) {
    const ref = useRef<HTMLSpanElement>(null);
    const prev = useRef(0);
    const reduce = useReducedMotion();
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        if (reduce) { el.textContent = euro(value); prev.current = value; return; }
        const c = animate(prev.current, value, { duration: 0.9, ease: [0.16, 1, 0.3, 1], onUpdate: v => { el.textContent = euro(Math.round(v / 100) * 100); } });
        prev.current = value;
        return () => c.stop();
    }, [value, reduce]);
    return <span ref={ref} className={className}>{euro(value)}</span>;
}

function ResultCard({ result, busy, error, ready, place, form, payload }: {
    result: Result | null; busy: boolean; error: string | null; ready: boolean; place: Place; form: Form; payload: Record<string, unknown> | null;
}) {
    if (!ready) {
        return (
            <div className="rounded-3xl border border-dashed border-white/15 bg-panel/30 p-8 text-center">
                <p className="text-ink">Indiquez la surface pour voir votre estimation</p>
                <p className="mt-2 text-sm text-muted">Elle s'affiche immédiatement et se met à jour à chaque modification.</p>
            </div>
        );
    }
    if (error && !result) return <div className="rounded-3xl border border-coral/40 bg-coral/10 p-6 text-sm text-ink">{error}</div>;
    if (!result) return <div className="rounded-3xl border border-white/10 bg-panel/60 p-10 flex items-center justify-center gap-3 text-muted"><Loader2 className="animate-spin" size={20} /> Analyse des ventes autour de l'adresse…</div>;
    const span = result.high - result.low || 1;
    return (
        <div className="space-y-4">
            <div className="relative overflow-hidden rounded-3xl border border-brass/30 bg-gradient-to-br from-panel via-panel to-[#0d1830] p-6 sm:p-7 shadow-[0_30px_90px_-30px_rgba(201,164,92,0.45)]">
                <div aria-hidden="true" className="absolute -top-24 -right-24 h-64 w-64 rounded-full bg-brass/20 blur-[80px]" />
                <div className="relative">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-xs uppercase tracking-[0.16em] text-brass">Estimation</p>
                        {busy && <Loader2 size={16} className="animate-spin text-muted" />}
                    </div>
                    <p className="mt-2 font-serif text-[2.6rem] sm:text-5xl leading-none text-ink tabular-nums"><AnimatedEuro value={result.value} /></p>
                    <p className="mt-2 text-sm text-muted">{form.kind === 'maison' ? 'Maison' : 'Appartement'} de {form.surface} m² · {place.city}</p>
                    {/* Range */}
                    <div className="mt-6">
                        <div className="relative h-2 rounded-full bg-gradient-to-r from-[#3b82f6]/40 via-brass/70 to-[#3b82f6]/40">
                            <motion.span className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-5 w-5 rounded-full bg-brass-light shadow-[0_0_20px_rgba(227,201,143,0.9)] ring-4 ring-canvas"
                                animate={{ left: `${((result.value - result.low) / span) * 100}%` }} transition={{ type: 'spring', stiffness: 120, damping: 18 }} />
                        </div>
                        <div className="mt-2 flex justify-between text-xs text-muted tabular-nums"><span>{euro(result.low)}</span><span>Fourchette probable</span><span>{euro(result.high)}</span></div>
                    </div>
                    <div className="mt-6 grid grid-cols-2 gap-3">
                        <Stat label="Prix au m²" value={euro(result.price_m2)} hint={`Marché : ${euro(result.market_m2)}`} />
                        <Stat label="Fiabilité" value={<span className="flex items-center gap-2">{result.reliability.label}<Dots n={result.reliability.score} /></span>} hint={`${result.sales} ventes ${result.scope}`} />
                        {result.trend && (
                            <Stat label="Marché sur 1 an" value={<span className={`flex items-center gap-1.5 ${result.trend.pct >= 0 ? 'text-sage' : 'text-coral'}`}>{result.trend.pct >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}{result.trend.pct > 0 ? '+' : ''}{result.trend.pct.toLocaleString('fr-FR')} %</span>}
                                hint={`${quarter(result.trend.from)} → ${quarter(result.trend.to)}`} />
                        )}
                        {result.dpe_effect !== null && form.dpe && (
                            <Stat label={`Effet du DPE ${form.dpe}`} value={<span className={result.dpe_effect >= 0 ? 'text-sage' : 'text-coral'}>{result.dpe_effect > 0 ? '+' : ''}{result.dpe_effect.toLocaleString('fr-FR')} %</span>} hint="Mesuré sur les ventes du département" />
                        )}
                    </div>
                    {result.adjustments.length > 0 && (
                        <div className="mt-5 flex flex-wrap gap-2">
                            {result.adjustments.map(a => (
                                <span key={a.label} className={`rounded-full px-3 py-1 text-xs border ${a.pct >= 0 ? 'border-sage/40 text-sage' : 'border-coral/40 text-coral'}`}>{a.label} {a.pct > 0 ? '+' : ''}{a.pct} %</span>
                            ))}
                        </div>
                    )}
                    {result.renovation && (
                        <div className="mt-5 rounded-2xl border border-sage/30 bg-sage/[0.07] p-4 text-sm text-ink-soft">
                            <b className="text-sage">+{euro(result.renovation.gain)}</b> de valeur possible après une rénovation énergétique jusqu'à la classe {result.renovation.target}, selon les écarts de prix mesurés dans votre département.
                        </div>
                    )}
                </div>
            </div>
            <Explanation result={result} form={form} place={place} />
            <LeadForm result={result} payload={payload} />
            <Comparables result={result} />
        </div>
    );
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
    return (
        <div className="rounded-2xl border border-white/10 bg-canvas/40 p-3.5">
            <p className="text-[11px] uppercase tracking-[0.14em] text-faint">{label}</p>
            <p className="mt-1 text-lg text-ink">{value}</p>
            {hint && <p className="mt-0.5 text-xs text-muted leading-snug">{hint}</p>}
        </div>
    );
}

function Dots({ n }: { n: number }) {
    return <span className="inline-flex gap-1" aria-label={`${n} sur 5`}>{[1, 2, 3, 4, 5].map(i => <span key={i} className={`h-1.5 w-1.5 rounded-full ${i <= n ? 'bg-brass-light' : 'bg-white/15'}`} />)}</span>;
}

// Plain-words explanation written by the AI once the estimate settles
function Explanation({ result, form, place }: { result: Result; form: Form; place: Place }) {
    const [text, setText] = useState<string | null>(null);
    const key = `${result.value}-${form.dpe}-${result.adjustments.length}`;
    useEffect(() => {
        setText(null);
        const ctl = new AbortController();
        const t = setTimeout(async () => {
            try {
                const res = await fetch('/api/estimate/explain', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctl.signal,
                    body: JSON.stringify({
                        city: place.city, kind: form.kind, surface: form.surface, value: result.value, low: result.low, high: result.high,
                        price_m2: result.price_m2, market_m2: result.market_m2, sales: result.sales, scope: result.scope, dpe: form.dpe,
                        dpe_effect: result.dpe_effect, adjustments: result.adjustments, trend_pct: result.trend?.pct ?? null, reliability: result.reliability.label,
                    }),
                });
                if (res.ok) setText((await res.json()).text);
            } catch { /* optional */ }
        }, 1400);
        return () => { clearTimeout(t); ctl.abort(); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);
    return (
        <div className="rounded-3xl border border-white/10 bg-panel/60 p-5">
            <p className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-faint"><Sparkles size={14} className="text-brass-light" /> Pourquoi ce prix</p>
            {text ? (
                <motion.p initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-2 text-sm text-ink-soft leading-relaxed">{text}</motion.p>
            ) : (
                <div className="mt-3 space-y-2" aria-hidden="true">{[92, 100, 70].map(w => <div key={w} className="h-3 rounded bg-white/[0.06] animate-pulse" style={{ width: `${w}%` }} />)}</div>
            )}
        </div>
    );
}

function LeadForm({ result, payload }: { result: Result; payload: Record<string, unknown> | null }) {
    const [project, setProject] = useState('vendre_3m');
    const [name, setName] = useState('');
    const [phone, setPhone] = useState('');
    const [email, setEmail] = useState('');
    const [consent, setConsent] = useState(false);
    const [website, setWebsite] = useState('');
    const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle');
    const [error, setError] = useState<string | null>(null);
    const submit = async () => {
        setError(null);
        if (name.trim().length < 2) return setError('Indiquez votre nom.');
        if (!phone.trim() && !email.trim()) return setError('Indiquez un téléphone ou un email.');
        if (!consent) return setError('Cochez la case pour accepter d\'être recontacté.');
        setState('busy');
        const res = await fetch('/api/estimate/lead', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ estimate: payload, value: result.value, low: result.low, high: result.high, name, phone: phone || null, email: email || null, project, consent, website, source: `${document.referrer || 'direct'} ${window.location.search}`.slice(0, 200) }),
        });
        if (res.ok) setState('done');
        else { setError(await errorDetail(res, "L'envoi a échoué, réessayez.")); setState('idle'); }
    };
    if (state === 'done') {
        return (
            <motion.div initial={{ scale: 0.97, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="rounded-3xl border border-sage/40 bg-sage/[0.08] p-6 text-center">
                <Check size={28} className="mx-auto text-sage" />
                <p className="mt-2 text-ink">Demande envoyée</p>
                <p className="mt-1 text-sm text-muted">Un conseiller de votre secteur vous recontacte rapidement pour affiner le prix, gratuitement et sans engagement.</p>
            </motion.div>
        );
    }
    return (
        <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6">
            <h2 className="text-lg text-ink">Affinez le prix avec un conseiller du secteur</h2>
            <p className="mt-1 text-sm text-muted">Gratuit et sans engagement. Un professionnel qui connaît votre quartier tient compte de ce qu'aucun algorithme ne voit : vue, exposition, état réel.</p>
            <div className="mt-4 space-y-3">
                <div className="flex flex-wrap gap-2">
                    {PROJECTS.map(([v, l]) => <Toggle key={v} on={project === v} onClick={() => setProject(v)}>{l}</Toggle>)}
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                    <input value={name} onChange={e => setName(e.target.value)} placeholder="Nom" autoComplete="name" className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink placeholder:text-faint outline-none focus:border-brass/70" />
                    <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Téléphone" inputMode="tel" autoComplete="tel" className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink placeholder:text-faint outline-none focus:border-brass/70" />
                    <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" type="email" autoComplete="email" className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink placeholder:text-faint outline-none focus:border-brass/70" />
                </div>
                <input value={website} onChange={e => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off" aria-hidden="true" className="hidden" />
                <label className="flex items-start gap-3 text-xs text-muted leading-relaxed cursor-pointer">
                    <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#C9A45C] shrink-0" />
                    <span>{CONSENT} <a href="/confidentialite" className="underline hover:text-ink">Confidentialité</a></span>
                </label>
                {error && <p role="alert" className="text-sm text-coral">{error}</p>}
                <GlowButton onClick={submit} className="w-full sm:w-auto">{state === 'busy' ? <Loader2 size={16} className="animate-spin" /> : <>Être rappelé gratuitement <ArrowRight size={16} /></>}</GlowButton>
            </div>
        </div>
    );
}

function Comparables({ result }: { result: Result }) {
    if (!result.comparables.length) return null;
    return (
        <div className="rounded-3xl border border-white/10 bg-panel/60 p-5">
            <p className="text-xs uppercase tracking-[0.14em] text-faint">Ventes comparables récentes</p>
            <ul className="mt-3 divide-y divide-white/[0.06]">
                {result.comparables.map((c, i) => (
                    <li key={i} className="py-2.5 flex items-center justify-between gap-3 text-sm">
                        <span className="min-w-0">
                            <span className="block text-ink truncate">{c.street}{c.commune ? `, ${c.commune}` : ''}</span>
                            <span className="text-xs text-muted">{new Date(c.date).toLocaleDateString('fr-FR', { month: 'short', year: 'numeric' })} · {c.surface} m²{c.rooms ? ` · ${c.rooms} p.` : ''}{c.distance !== null ? ` · ${c.distance < 1000 ? `${c.distance} m` : `${(c.distance / 1000).toFixed(1)} km`}` : ''}</span>
                        </span>
                        <span className="text-right shrink-0"><span className="block text-ink tabular-nums">{euro(c.price)}</span><span className="text-xs text-muted tabular-nums">{euro(c.adjusted_m2)}/m²</span></span>
                    </li>
                ))}
            </ul>
            <p className="mt-3 text-xs text-faint">{result.sales} ventes {result.scope} ({result.period}), prix actualisés. Source : DVF, DGFiP.</p>
        </div>
    );
}

// --- Explanations and FAQ ---

// Also in the prerendered page, with the FAQ structured data (scripts/seo/prerender.mjs)
const FAQ: [string, string][] = faqData.map(f => [f.q, f.a]);

function SeoContent() {
    const [open, setOpen] = useState<number | null>(0);
    return (
        <section className="max-w-5xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
            <Reveal>
                <h2 className="text-2xl sm:text-4xl text-ink text-center">Une estimation calculée sur les vraies ventes de votre quartier</h2>
            </Reveal>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
                {[
                    ['1', 'Les ventes réelles', "Les prix de vente enregistrés chez les notaires (DVF), autour de votre adresse, pour des biens de même type et de surface comparable."],
                    ['2', 'L\'étiquette énergie', "L'écart de prix entre classes DPE, mesuré sur plus d'un million de ventes, appliqué à votre bien."],
                    ['3', 'Vos atouts', "État, étage, balcon, terrasse, parking : des ajustements mesurés, chacun affiché avec son poids."],
                ].map(([n, t, d], i) => (
                    <Reveal key={n} delay={i * 0.08}>
                        <div className="h-full rounded-3xl border border-white/10 bg-panel/60 p-6">
                            <span className="font-serif text-3xl text-brass-light">{n}</span>
                            <h3 className="mt-3 text-lg text-ink">{t}</h3>
                            <p className="mt-2 text-sm text-muted leading-relaxed">{d}</p>
                        </div>
                    </Reveal>
                ))}
            </div>
            <div className="mt-14">
                <h2 className="text-2xl sm:text-3xl text-ink">Questions fréquentes</h2>
                <div className="mt-6 divide-y divide-white/[0.08] rounded-3xl border border-white/10 bg-panel/40">
                    {FAQ.map(([q, a], i) => (
                        <div key={q}>
                            <button type="button" onClick={() => setOpen(open === i ? null : i)} className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left">
                                <h3 className="text-[15px] sm:text-base text-ink font-sans">{q}</h3>
                                <ChevronDown size={18} className={`text-muted shrink-0 transition-transform ${open === i ? 'rotate-180' : ''}`} />
                            </button>
                            <AnimatePresence initial={false}>
                                {open === i && (
                                    <motion.p initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden px-5 text-sm text-muted leading-relaxed">
                                        <span className="block pb-4">{a}</span>
                                    </motion.p>
                                )}
                            </AnimatePresence>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
