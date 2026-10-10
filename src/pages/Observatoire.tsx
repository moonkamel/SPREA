import { useMemo, useState } from 'react';
import { ArrowDownUp, Search } from 'lucide-react';
import { Link, navigate } from '../router';
import { departmentSlug, useSeo } from '../seo';
// Figures exported monthly with the green value (scripts/seo/export_observatoire.py)
import OBSERVATOIRE from '../data/observatoire.json';
import { Button, Card, DpeBadge, type DPEClass } from '../ui';
import { SiteFooter, SiteHeader } from './site';

type Kind = 'maisons' | 'appartements';
interface Series { sales: number; premium: Record<DPEClass, number>; mix: Record<DPEClass, number> }
interface Department { code: string; name: string; maisons?: Series; appartements?: Series }
interface Data { period: string; updated: string; total_sales: number; national: Partial<Record<Kind, Series>>; departments: Department[] }

const LABELS: DPEClass[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
// Categorical pair validated on the dark surface (lightness, chroma, colour-blind separation, contrast)
const SERIES: { key: Kind; name: string; color: string }[] = [
    { key: 'maisons', name: 'Maisons', color: '#B88A2E' },
    { key: 'appartements', name: 'Appartements', color: '#5590E0' },
];

const pct = (v: number | undefined | null) => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`);
const int = (v: number) => v.toLocaleString('fr-FR');
const period = (p?: string) => (p ? p.replace(/T\d/g, '').split('-').filter((x, i, a) => a.indexOf(x) === i).join(' à ') : '');

function ClassChart({ series }: { series: Partial<Record<Kind, Series>> }) {
    const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null);
    const values = SERIES.flatMap(s => LABELS.map(c => series[s.key]?.premium[c] ?? 0));
    const max = Math.max(10, Math.ceil(Math.max(...values.map(Math.abs)) / 5) * 5);
    const present = SERIES.filter(s => series[s.key]);

    return (
        <div className="relative" onMouseLeave={() => setHover(null)}>
            <div className="flex flex-wrap gap-4 text-sm text-ink-soft mb-4" aria-label="Légende">
                {present.map(s => (
                    <span key={s.key} className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />{s.name}</span>
                ))}
            </div>
            <div className="space-y-2.5">
                {LABELS.map(c => (
                    <div key={c} className="grid grid-cols-[2.25rem_1fr] items-center gap-3">
                        <DpeBadge label={c} size="sm" />
                        <div className="relative mx-12">
                            {/* Zero line: price of a D-rated dwelling */}
                            <div className="absolute inset-y-0 left-1/2 w-px bg-line" aria-hidden="true" />
                            {c === 'D' ? (
                                <p className="h-[22px] text-xs text-faint pl-[calc(50%+8px)] leading-[22px]">référence</p>
                            ) : present.map(s => {
                                const v = series[s.key]!.premium[c];
                                const width = `${(Math.abs(v) / max) * 50}%`;
                                const positive = v >= 0;
                                const text = `${s.name} classe ${c} : ${pct(v)} par rapport à D (${int(series[s.key]!.sales)} ventes)`;
                                return (
                                    <div key={s.key} className="relative h-[11px] mb-[2px]"
                                        onMouseMove={e => setHover({ text, x: e.nativeEvent.offsetX + (e.currentTarget.offsetLeft || 0), y: e.currentTarget.offsetTop })}>
                                        <div className="absolute top-0 h-full"
                                            style={{ background: s.color, width, left: positive ? '50%' : undefined, right: positive ? undefined : '50%',
                                                borderRadius: positive ? '0 4px 4px 0' : '4px 0 0 4px' }}
                                            aria-label={text} role="img" />
                                        <span className="absolute top-1/2 -translate-y-1/2 text-[11px] text-ink-soft tabular-nums whitespace-nowrap"
                                            style={positive ? { left: `calc(50% + ${width} + 6px)` } : { right: `calc(50% + ${width} + 6px)` }}>
                                            {pct(v)}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
            <div className="mt-2 grid grid-cols-[2.25rem_1fr] gap-3 text-[11px] text-faint">
                <span />
                <div className="mx-12 flex justify-between whitespace-nowrap"><span>−{max} %</span><span className="hidden sm:inline">prix d'un logement D</span><span>+{max} %</span></div>
            </div>
            {hover && (
                <div className="pointer-events-none absolute z-10 rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-ink shadow-lg"
                    style={{ left: Math.min(hover.x + 12, 520), top: hover.y + 40 }}>
                    {hover.text}
                </div>
            )}
        </div>
    );
}

type SortKey = 'name' | 'sales' | 'maisons' | 'appartements';

export const departmentPath = (d: { name: string; code: string }) => `/observatoire/${departmentSlug(d.name, d.code)}`;

// Plain-language summary of a department (same wording in the prerendered page)
function summary(d: Department, national: Data['national']): string {
    const parts: string[] = [];
    const h = d.maisons, a = d.appartements;
    if (h) {
        const gap = h.premium.G - (national.maisons?.premium.G ?? h.premium.G);
        parts.push(`Dans le département ${d.name === 'Paris' ? 'de Paris' : `${d.name} (${d.code})`}, une maison classée G se vend ${pct(h.premium.G).replace('−', '')} moins cher qu'une maison classée D comparable`
            + (Math.abs(gap) >= 1 ? `, soit ${Math.abs(gap).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} points ${gap < 0 ? 'de plus' : 'de moins'} qu'en moyenne en France.` : ', comme en moyenne en France.'));
    }
    if (a) parts.push(`Pour un appartement, l'écart entre G et D atteint ${pct(a.premium.G).replace('−', '')}.`);
    return parts.join(' ');
}

export default function ObservatoirePage({ slug }: { slug?: string }) {
    const data = OBSERVATOIRE as unknown as Data;
    const dep = data.departments.find(d => departmentSlug(d.name, d.code) === slug)?.code || '';
    const setDep = (code: string) => {
        const d = data.departments.find(x => x.code === code);
        navigate(d ? departmentPath(d) : '/observatoire');
    };
    const [query, setQuery] = useState('');
    const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: 'maisons', asc: true });

    const selected = data.departments.find(d => d.code === dep);
    useSeo(selected ? {
        title: `Valeur verte ${selected.name} (${selected.code}) : prix selon le DPE · SPREA`,
        description: `${summary(selected, data.national)} Calculé sur ${int((selected.maisons?.sales || 0) + (selected.appartements?.sales || 0))} ventes réelles rapprochées de leur DPE.`,
        path: departmentPath(selected),
    } : {
        title: 'Observatoire de la valeur verte : prix des logements selon le DPE · SPREA',
        description: "Combien vaut un logement selon son DPE ? Écarts de prix entre classes énergétiques mesurés sur plus d'un million de ventes réelles, en France et par département.",
        path: '/observatoire',
    });
    const series = selected ? { maisons: selected.maisons, appartements: selected.appartements } : data?.national || {};

    const rows = useMemo(() => {
        if (!data) return [];
        const q = query.trim().toLowerCase();
        const value = (d: Department): number | string => {
            if (sort.key === 'name') return d.code;
            if (sort.key === 'sales') return (d.maisons?.sales || 0) + (d.appartements?.sales || 0);
            return d[sort.key]?.premium.G ?? (sort.asc ? 999 : -999);
        };
        return data.departments
            .filter(d => !q || d.name.toLowerCase().includes(q) || d.code.toLowerCase().startsWith(q))
            .sort((a, b) => {
                const va = value(a), vb = value(b);
                const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number);
                return sort.asc ? cmp : -cmp;
            });
    }, [data, query, sort]);

    const sortBy = (key: SortKey) => setSort(s => ({ key, asc: s.key === key ? !s.asc : key !== 'sales' }));
    const th = (key: SortKey, label: string, align = 'text-right') => (
        <th className={`font-normal py-2 ${align}`}>
            <button type="button" onClick={() => sortBy(key)} className={`inline-flex items-center gap-1 hover:text-ink ${sort.key === key ? 'text-ink' : ''}`}>
                {label}<ArrowDownUp size={12} />
            </button>
        </th>
    );

    // Tiles: the selected department, or France
    const houses = selected ? selected.maisons : data.national.maisons;
    const flats = selected ? selected.appartements : data.national.appartements;
    const where = selected ? ` · ${selected.name}` : '';

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-10 space-y-8">
                <section>
                    <p className="text-sm text-brass">
                        {selected ? <><Link to="/observatoire" className="hover:underline">Observatoire de la valeur verte</Link> · {selected.name}</> : 'Observatoire de la valeur verte'}
                    </p>
                    <h1 className="mt-2 text-3xl sm:text-5xl text-ink leading-tight">
                        {selected ? `Valeur verte ${selected.name === 'Paris' ? 'à Paris' : `dans le département ${selected.name} (${selected.code})`}` : "Combien le DPE pèse-t-il sur le prix d'un logement ?"}
                    </h1>
                    {selected && <p className="mt-4 text-lg text-ink-soft max-w-3xl">{summary(selected, data.national)}</p>}
                    <p className="mt-4 text-muted max-w-3xl">
                        Écarts de prix entre classes énergétiques, mesurés sur {data ? int(data.total_sales) : '…'} ventes réelles rapprochées une à une du DPE
                        du logement vendu ({data ? period(data.period) : '…'}). Mis à jour chaque mois.
                    </p>
                </section>

                {(houses || flats) && (
                    <section className="grid sm:grid-cols-3 gap-4">
                        <Card className="p-5">
                            <p className="text-sm text-muted">Une maison classée G{where}</p>
                            <p className="mt-1 font-serif text-4xl text-ink tabular-nums">{pct(houses?.premium.G)}</p>
                            <p className="text-sm text-muted">par rapport à une maison classée D</p>
                        </Card>
                        <Card className="p-5">
                            <p className="text-sm text-muted">Un appartement classé G{where}</p>
                            <p className="mt-1 font-serif text-4xl text-ink tabular-nums">{pct(flats?.premium.G)}</p>
                            <p className="text-sm text-muted">par rapport à un appartement classé D</p>
                        </Card>
                        <Card className="p-5">
                            <p className="text-sm text-muted">Une maison classée A{where}</p>
                            <p className="mt-1 font-serif text-4xl text-ink tabular-nums">{pct(houses?.premium.A)}</p>
                            <p className="text-sm text-muted">par rapport à une maison classée D</p>
                        </Card>
                    </section>
                )}

                {data && (
                    <Card className="p-5 sm:p-6">
                        <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
                            <div>
                                <h2 className="text-xl text-ink">Écart de prix par classe DPE</h2>
                                <p className="text-sm text-muted">À emplacement, surface, époque de construction et date de vente comparables, par rapport à la classe D.</p>
                            </div>
                            <select value={dep} onChange={e => setDep(e.target.value)} aria-label="Département"
                                className="h-10 rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                                <option value="">France entière</option>
                                {data.departments.map(d => <option key={d.code} value={d.code}>{d.code} · {d.name}</option>)}
                            </select>
                        </div>
                        <ClassChart series={series} />
                        {selected && !selected.maisons && <p className="mt-3 text-xs text-faint">Pas assez de ventes de maisons rapprochées de leur DPE dans ce département.</p>}
                    </Card>
                )}

                {data && (
                    <Card className="p-5 sm:p-6">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <h2 className="text-xl text-ink">Par département</h2>
                            <div className="flex items-center rounded-xl border border-line bg-raised">
                                <Search size={14} className="ml-3 text-faint" />
                                <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Département"
                                    className="bg-transparent px-2 h-9 text-sm text-ink outline-none w-40" aria-label="Rechercher un département" />
                            </div>
                        </div>
                        <div className="mt-3 overflow-x-auto">
                            <table className="w-full text-sm min-w-[560px]">
                                <thead className="text-faint">
                                    <tr>
                                        {th('name', 'Département', 'text-left')}
                                        {th('sales', 'Ventes rapprochées')}
                                        {th('maisons', 'Maison G vs D')}
                                        <th className="font-normal py-2 text-right">Maison F vs D</th>
                                        {th('appartements', 'Appart. G vs D')}
                                        <th className="font-normal py-2 text-right">Appart. F vs D</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-line/70 tabular-nums">
                                    {rows.map(d => (
                                        <tr key={d.code} className={`hover:bg-raised/50 ${d.code === dep ? 'bg-raised/60' : ''}`}>
                                            <td className="py-2 text-ink-soft"><span className="text-faint mr-2">{d.code}</span><Link to={departmentPath(d)} className="hover:text-brass-light hover:underline">{d.name}</Link></td>
                                            <td className="text-right text-muted">{int((d.maisons?.sales || 0) + (d.appartements?.sales || 0))}</td>
                                            <td className="text-right text-ink">{pct(d.maisons?.premium.G)}</td>
                                            <td className="text-right text-ink-soft">{pct(d.maisons?.premium.F)}</td>
                                            <td className="text-right text-ink">{pct(d.appartements?.premium.G)}</td>
                                            <td className="text-right text-ink-soft">{pct(d.appartements?.premium.F)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                )}

                <Card className="p-5 sm:p-6 grid sm:grid-cols-[1fr_auto] gap-4 items-center">
                    <div>
                        <h2 className="text-xl text-ink">Vous êtes agent immobilier ?</h2>
                        <p className="mt-1 text-sm text-muted">Avec SPREA, chiffrez en rendez-vous les travaux, les aides et la valeur d'un bien avant et après rénovation, et repérez les passoires de votre secteur.</p>
                    </div>
                    <Link to="/demo"><Button>Faire la visite guidée</Button></Link>
                </Card>

                <section className="text-sm text-muted space-y-2 max-w-4xl">
                    <h2 className="text-lg text-ink">Méthode</h2>
                    <p>
                        Chaque vente d'un seul logement des Demandes de valeurs foncières (DVF, DGFiP) depuis 2022 est rapprochée du DPE de ce logement publié par
                        l'ADEME : même adresse, même type de bien, surface proche, DPE établi avant la vente. L'écart de prix entre classes est estimé par une
                        régression du prix au m² sur la classe DPE, l'époque de construction, la surface et le trimestre de vente, à emplacement identique
                        (secteurs d'environ 1 km). Les estimations départementales s'appuient sur l'estimation nationale quand les ventes sont peu nombreuses,
                        et les écarts ne peuvent pas croître de A vers G. Départements affichés à partir de 300 ventes rapprochées : la Corse et la Lozère n'y
                        arrivent pas encore. L'Alsace-Moselle et Mayotte ne sont pas couvertes par DVF, et les DPE de Guadeloupe, Martinique, Guyane et
                        La Réunion ne figurent pas dans la base nationale de l'ADEME.
                    </p>
                    <p className="text-xs text-faint">
                        Sources : DVF (DGFiP, Etalab) et DPE des logements existants (ADEME), Licence Ouverte 2.0. Reprise libre avec la mention
                        « Observatoire de la valeur verte SPREA ». {data?.updated && `Dernière mise à jour : ${new Date(data.updated).toLocaleDateString('fr-FR')}.`}
                    </p>
                </section>
            </main>
            <SiteFooter />
        </div>
    );
}
