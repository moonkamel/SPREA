import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Building2, Home as HomeIcon, MapPin, Search, TrendingDown, TrendingUp } from 'lucide-react';
import { SiteFooter, SiteHeader, NotFound } from './site';
import { Link, navigate } from '../router';
import { useSeo } from '../seo';
import { DPE_COLORS, DPE_LABELS, type DPEClass } from '../ui';
import { GlowButton, Reveal } from '../views/home/fx';

// « Prix m² à <commune> » pages (/prix-m2/<slug>-<insee>) and their list
// (/prix-m2), from the DVF figures built by scripts/seo/city_prices.py and
// served as one file per department (public/prix/<dep>.json). The same
// figures are prerendered for search engines (scripts/seo/prerender.mjs).

type KindKey = 'appartement' | 'maison';
interface Figure {
    m2: number; q25: number; q75: number; n: number; surface: number; price: number;
    years: Record<string, { m2: number; n: number }>;
    rooms: Record<string, { m2: number; price: number; surface: number; n: number }>;
}
interface Commune {
    code: string; name: string; slug: string; dep: string; depName: string; pop: number | null;
    parent: string | null; children?: string[]; near: string[]; sales: number; kinds: Partial<Record<KindKey, Figure>>;
}
interface DepFile {
    dep: string; depName: string; years: number[]; updated: string;
    dpe: Partial<Record<KindKey, Record<DPEClass, number>>> | null;
    communes: Record<string, Commune>; names: Record<string, { name: string; slug: string; m2: number | null }>;
}
interface IndexRow { c: string; n: string; s: string; d: string; p: number; a: number | null; m: number | null; k: number }

const euro = (n: number) => `${Math.round(n).toLocaleString('fr-FR')} €`;
export const depOf = (insee: string) => (insee.startsWith('97') ? insee.slice(0, 3) : insee.slice(0, 2));
const KIND_LABEL: Record<KindKey, string> = { appartement: 'Appartements', maison: 'Maisons' };

function change(f: Figure): { pct: number; from: string; to: string } | null {
    const ys = Object.keys(f.years).sort();
    if (ys.length < 2) return null;
    const a = f.years[ys[0]].m2, b = f.years[ys[ys.length - 1]].m2;
    return { pct: Math.round(((b - a) / a) * 1000) / 10, from: ys[0], to: ys[ys.length - 1] };
}

export default function CityPricePage({ slug }: { slug: string }) {
    const insee = slug.split('-').pop()?.toUpperCase() || '';
    const [data, setData] = useState<DepFile | null>(null);
    const [failed, setFailed] = useState(false);
    useEffect(() => {
        if (!/^[0-9][0-9AB][0-9]{3}$/.test(insee)) { setFailed(true); return; }
        setData(null); setFailed(false);
        fetch(`/prix/${depOf(insee)}.json`).then(r => (r.ok ? r.json() : Promise.reject())).then(setData).catch(() => setFailed(true));
    }, [insee]);
    const c = data?.communes[insee];
    const apt = c?.kinds.appartement, house = c?.kinds.maison;
    const main = apt || house;
    const period = data ? `${data.years[1] ?? data.years[0]}-${data.years[0]}` : '';
    useSeo({
        title: c ? `Prix m² ${c.name} : prix immobilier au m² ${new Date().getFullYear()} (maisons, appartements) | SPREA` : 'Prix m² | SPREA',
        description: c && main ? `Prix au m² à ${c.name} (${c.dep}) : ${apt ? `appartements ${euro(apt.m2)}` : ''}${apt && house ? ', ' : ''}${house ? `maisons ${euro(house.m2)}` : ''} le m², d'après ${c.sales} ventes réelles (DVF ${period}). Évolution, prix par nombre de pièces et estimation gratuite.` : undefined,
        path: c ? `/prix-m2/${c.slug}` : undefined,
    });
    if (failed || (data && !c)) return <NotFound />;
    if (!data || !c) return <div className="min-h-screen bg-canvas"><SiteHeader /></div>;
    const parent = c.parent ? data.names[c.parent] : null;
    const dpe = data.dpe?.[apt ? 'appartement' : 'maison'];
    return (
        <div className="min-h-screen flex flex-col bg-canvas overflow-x-clip">
            <SiteHeader />
            <main className="flex-1">
                <section className="relative overflow-hidden">
                    <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_50%_60%_at_85%_10%,rgba(40,120,255,0.16),transparent_70%),radial-gradient(ellipse_50%_50%_at_5%_0%,rgba(201,164,92,0.12),transparent_70%)]" />
                    <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-8 sm:pt-12 pb-8">
                        <nav className="text-xs text-faint flex flex-wrap gap-1.5" aria-label="Fil d'Ariane">
                            <Link to="/prix-m2" className="hover:text-ink">Prix m² par commune</Link><span>›</span>
                            <span>{c.depName} ({c.dep})</span>
                            {parent && <><span>›</span><Link to={`/prix-m2/${parent.slug}`} className="hover:text-ink">{parent.name}</Link></>}
                        </nav>
                        <h1 className="mt-4 text-[2rem] sm:text-5xl leading-[1.08] text-ink">Prix m² à {c.name}</h1>
                        <p className="mt-3 max-w-2xl text-[15px] sm:text-base text-ink-soft/90">
                            Prix médian au m² des ventes réellement enregistrées à {c.name} ({period}), d'après la base DVF de la DGFiP : {c.sales.toLocaleString('fr-FR')} ventes de maisons et d'appartements.
                        </p>
                        <div className="mt-8 grid gap-4 sm:grid-cols-2">
                            {(['appartement', 'maison'] as KindKey[]).map(k => {
                                const f = c.kinds[k];
                                const ch = f ? change(f) : null;
                                return (
                                    <div key={k} className="rounded-3xl border border-white/10 bg-panel/70 p-6">
                                        <p className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-brass">{k === 'appartement' ? <Building2 size={15} /> : <HomeIcon size={15} />} {KIND_LABEL[k]}</p>
                                        {f ? (
                                            <>
                                                <p className="mt-2 font-serif text-4xl sm:text-5xl text-ink tabular-nums">{euro(f.m2)}<span className="text-lg text-muted font-sans"> /m²</span></p>
                                                <p className="mt-1 text-sm text-muted">La moitié des ventes entre {euro(f.q25)} et {euro(f.q75)} le m² · {f.n.toLocaleString('fr-FR')} ventes</p>
                                                <p className="mt-3 text-sm text-ink-soft">Bien type : {f.surface} m² vendu {euro(f.price)}</p>
                                                {ch && (
                                                    <p className={`mt-2 inline-flex items-center gap-1.5 text-sm ${ch.pct >= 0 ? 'text-sage' : 'text-coral'}`}>
                                                        {ch.pct >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}{ch.pct > 0 ? '+' : ''}{ch.pct.toLocaleString('fr-FR')} % entre {ch.from} et {ch.to}
                                                    </p>
                                                )}
                                            </>
                                        ) : <p className="mt-3 text-sm text-muted">Trop peu de ventes pour publier un prix fiable.</p>}
                                    </div>
                                );
                            })}
                        </div>
                        <div className="mt-6 flex flex-col sm:flex-row sm:items-center gap-4 rounded-3xl border border-brass/30 bg-gradient-to-r from-brass/[0.10] to-transparent p-5">
                            <p className="flex-1 text-ink">Combien vaut votre bien à {c.name}&nbsp;? <span className="text-muted">Estimation gratuite et immédiate, calculée sur les ventes de votre rue.</span></p>
                            <GlowButton onClick={() => navigate(`/estimation?commune=${encodeURIComponent(c.name)}`)}>Estimer mon bien <ArrowRight size={16} /></GlowButton>
                        </div>
                    </div>
                </section>

                <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-16 space-y-6">
                    <div className="grid gap-4 lg:grid-cols-2">
                        {(['appartement', 'maison'] as KindKey[]).filter(k => c.kinds[k] && Object.keys(c.kinds[k]!.years).length > 1).map(k => (
                            <Reveal key={k}><YearBars title={`${KIND_LABEL[k]} : prix médian au m² par année`} f={c.kinds[k]!} /></Reveal>
                        ))}
                    </div>
                    {(apt?.rooms && Object.keys(apt.rooms).length > 0) || (house?.rooms && Object.keys(house.rooms).length > 0) ? (
                        <Reveal>
                            <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6 overflow-x-auto">
                                <h2 className="text-xl text-ink">Prix selon le nombre de pièces</h2>
                                <table className="mt-4 w-full min-w-[480px] text-sm">
                                    <thead><tr className="text-left text-faint"><th className="font-normal py-2">Pièces</th>
                                        {apt && <th className="font-normal">Appartement · prix médian</th>}{house && <th className="font-normal">Maison · prix médian</th>}</tr></thead>
                                    <tbody className="divide-y divide-white/[0.06]">
                                        {['1', '2', '3', '4', '5'].filter(r => apt?.rooms[r] || house?.rooms[r]).map(r => (
                                            <tr key={r}>
                                                <td className="py-2.5 text-ink">{r === '5' ? '5 et plus' : r === '1' ? (apt ? '1 (studio)' : '1') : r}</td>
                                                {apt && <td className="text-ink-soft tabular-nums">{apt.rooms[r] ? `${euro(apt.rooms[r].price)} · ${apt.rooms[r].surface} m² · ${euro(apt.rooms[r].m2)}/m²` : '–'}</td>}
                                                {house && <td className="text-ink-soft tabular-nums">{house.rooms[r] ? `${euro(house.rooms[r].price)} · ${house.rooms[r].surface} m² · ${euro(house.rooms[r].m2)}/m²` : '–'}</td>}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Reveal>
                    ) : null}
                    {dpe && (
                        <Reveal>
                            <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6">
                                <h2 className="text-xl text-ink">L'étiquette énergie pèse sur le prix</h2>
                                <p className="mt-1 text-sm text-muted">Écart de prix d'un{apt ? ' appartement' : 'e maison'} selon sa classe DPE, par rapport à la classe D, mesuré sur les ventes du département ({data.depName}).</p>
                                <div className="mt-4 grid grid-cols-7 gap-1.5 sm:gap-2">
                                    {DPE_LABELS.map(l => (
                                        <div key={l} className="text-center">
                                            <span className="block rounded-lg py-2 font-bold" style={{ background: DPE_COLORS[l].bg, color: DPE_COLORS[l].fg }}>{l}</span>
                                            <span className="mt-1 block text-xs text-ink-soft tabular-nums">{dpe[l] > 0 ? '+' : ''}{dpe[l].toLocaleString('fr-FR')} %</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </Reveal>
                    )}
                    {c.children && c.children.length > 0 && (
                        <Links title={`Prix m² par arrondissement de ${c.name}`} codes={c.children} names={data.names} />
                    )}
                    {c.near.length > 0 && <Links title={parent ? `Autres arrondissements de ${parent.name}` : `Prix m² autour de ${c.name}`} codes={c.near} names={data.names} />}
                    <p className="text-xs text-faint">Source : Demandes de valeurs foncières (DVF), DGFiP, ventes {period} de logements seuls (hors ventes mixtes et valeurs aberrantes). Mise à jour le {new Date(data.updated).toLocaleDateString('fr-FR')}. Les prix médians donnent un ordre de grandeur : la valeur d'un bien dépend de sa rue, de son état et de son étiquette énergie.</p>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}

// Median price per m2 per year, one series: bars on a baseline, latest value labelled, others on hover
function YearBars({ title, f }: { title: string; f: Figure }) {
    const years = Object.keys(f.years).sort();
    const max = Math.max(...years.map(y => f.years[y].m2));
    const [hover, setHover] = useState<string | null>(null);
    const shown = hover ?? years[years.length - 1];
    return (
        <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6">
            <h2 className="text-base text-ink font-sans font-medium">{title}</h2>
            <p className="mt-1 text-sm text-muted"><span className="text-ink tabular-nums">{euro(f.years[shown].m2)}/m²</span> en {shown} · {f.years[shown].n.toLocaleString('fr-FR')} ventes</p>
            <div className="mt-5 flex items-end gap-3 h-36 border-b border-white/15" role="img" aria-label={years.map(y => `${y} : ${euro(f.years[y].m2)} le m²`).join(', ')}>
                {years.map((y, i) => {
                    const last = i === years.length - 1;
                    return (
                        <button key={y} type="button" onMouseEnter={() => setHover(y)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(y)} onBlur={() => setHover(null)}
                            className="group flex-1 h-full flex flex-col justify-end items-center" aria-label={`${y} : ${euro(f.years[y].m2)} le m²`}>
                            {last && <span className="mb-1 text-xs text-ink-soft tabular-nums">{euro(f.years[y].m2)}</span>}
                            <span className={`w-full max-w-16 rounded-t transition-opacity ${shown === y ? 'bg-brass' : 'bg-brass/45 group-hover:bg-brass/70'}`}
                                style={{ height: `${Math.max(6, (f.years[y].m2 / max) * 100)}%` }} />
                        </button>
                    );
                })}
            </div>
            <div className="mt-2 flex gap-3 text-xs text-muted">{years.map(y => <span key={y} className="flex-1 text-center">{y}</span>)}</div>
        </div>
    );
}

function Links({ title, codes, names }: { title: string; codes: string[]; names: DepFile['names'] }) {
    return (
        <Reveal>
            <div className="rounded-3xl border border-white/10 bg-panel/60 p-5 sm:p-6">
                <h2 className="text-xl text-ink">{title}</h2>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {codes.filter(code => names[code]).map(code => (
                        <Link key={code} to={`/prix-m2/${names[code].slug}`} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 px-4 py-3 text-sm hover:border-brass/50 transition-colors">
                            <span className="text-ink truncate">{names[code].name}</span>
                            {names[code].m2 && <span className="text-muted tabular-nums shrink-0">{euro(names[code].m2!)}/m²</span>}
                        </Link>
                    ))}
                </div>
            </div>
        </Reveal>
    );
}

// --- List of the communes: /prix-m2 ---

export function CityPriceIndexPage() {
    useSeo({
        title: 'Prix du m² par commune : prix immobilier de toutes les villes de France | SPREA',
        description: "Prix au m² des maisons et des appartements dans chaque commune de France, calculé sur les ventes réelles (DVF). Cherchez votre ville : prix médian, évolution, prix par nombre de pièces.",
        path: '/prix-m2',
    });
    const [index, setIndex] = useState<{ updated: string; years: number[]; deps: Record<string, string>; communes: IndexRow[] } | null>(null);
    const [q, setQ] = useState('');
    useEffect(() => { import('../data/prix_index.json').then(m => setIndex(m.default as never)); }, []);
    const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const found = useMemo(() => {
        if (!index || q.trim().length < 2) return [];
        const n = norm(q.trim());
        return index.communes.filter(r => norm(r.n).includes(n) || r.c.startsWith(q.trim())).slice(0, 12);
    }, [index, q]);
    const top = index?.communes.filter(r => !/^(751|6938|132)\d\d$/.test(r.c)).slice(0, 48) ?? [];
    return (
        <div className="min-h-screen flex flex-col bg-canvas overflow-x-clip">
            <SiteHeader />
            <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-10 sm:py-14">
                <h1 className="text-[2rem] sm:text-5xl leading-[1.08] text-ink">Prix du m² par commune</h1>
                <p className="mt-3 max-w-2xl text-[15px] sm:text-base text-ink-soft/90">Le prix médian au m² des maisons et des appartements dans {index ? `${index.communes.length.toLocaleString('fr-FR')} communes` : 'chaque commune'} de France, calculé sur les ventes réelles enregistrées par l'administration fiscale (DVF).</p>
                <label className="mt-8 flex items-center gap-3 rounded-2xl border border-white/15 bg-panel/80 px-4 h-14 focus-within:border-brass/70">
                    <Search size={20} className="text-brass" />
                    <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Votre commune (ex. Lille, Annecy, Paris 15e)" aria-label="Commune"
                        className="flex-1 bg-transparent text-base text-ink placeholder:text-faint outline-none" />
                </label>
                {found.length > 0 && (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {found.map(r => <Row key={r.c} r={r} deps={index!.deps} />)}
                    </div>
                )}
                <h2 className="mt-12 text-2xl text-ink">Les villes où l'on vend le plus</h2>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {top.map(r => <Row key={r.c} r={r} deps={index!.deps} />)}
                </div>
            </main>
            <SiteFooter />
        </div>
    );
}

function Row({ r, deps }: { r: IndexRow; deps: Record<string, string> }) {
    return (
        <Link to={`/prix-m2/${r.s}`} className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-panel/50 px-4 py-3 text-sm hover:border-brass/50 transition-colors">
            <span className="min-w-0"><span className="flex items-center gap-1.5 text-ink truncate"><MapPin size={14} className="text-brass shrink-0" />{r.n}</span><span className="text-xs text-faint">{deps[r.d] || r.d} ({r.d})</span></span>
            <span className="text-right text-xs text-muted tabular-nums shrink-0">
                {r.a && <span className="block">Appart. {euro(r.a)}/m²</span>}{r.m && <span className="block">Maison {euro(r.m)}/m²</span>}
            </span>
        </Link>
    );
}
