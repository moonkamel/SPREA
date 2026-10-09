import { useEffect, useState } from 'react';
import { AlertTriangle, Building2, CheckCircle2, Loader2 } from 'lucide-react';
import { DpeBadge, Step, eurRange, num } from '../ui';
import type { DPEClass } from '../ui';
import { useAccount } from '../account';
import type { PropertyData } from '../model';

interface Copro {
    immat: string; name: string | null; lots_main: number | null; lots_housing: number | null; lots_parking: number | null;
    period: string | null; syndic_type: string | null; syndic_name: string | null; mandate_end: string | null;
    aided: boolean; in_pdp: boolean; qpv: string | null; match: 'immat' | 'position' | 'corner';
}
interface Obligation { id: string; title: string; since: string | null; status: 'due' | 'upcoming' | 'check' | 'done'; detail: string }
interface Work { id: string; name: string; reason: string; low: number; high: number }
interface Sheet {
    copro: Copro | null;
    building_dpe: { label: DPEClass; date_fr: string; number: string } | null;
    apartments: { count: number; distribution: Record<DPEClass, number> };
    dimensions: { surface: number | null; levels: number; dwellings: number };
    period: string | null;
    obligations: Obligation[];
    works: Work[]; total: [number, number] | null;
    estimate: { share: number; share_low: number; share_high: number; net_low: number; net_high: number; aid_rates: [number, number] } | null;
    works_source: 'immeuble' | 'appartement';
    works_note: string | null;
}

const dateFr = (iso: string) => iso.slice(0, 10).split('-').reverse().join('/');
const pct = (n: number) => `${(n * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;

function Fact({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <dt className="text-xs text-faint">{label}</dt>
            <dd className="text-sm text-ink">{value}</dd>
        </div>
    );
}

// Apartments: the copropriété (national registry), the collective DPE, the
// legal obligations and the collective works to come, with the flat's share
export default function BuildingSheet({ property, n }: { property: PropertyData; n: number }) {
    const { authedFetch } = useAccount();
    const [sheet, setSheet] = useState<Sheet | null>(null);
    const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');
    const apartment = (property.buildingType || '').toLowerCase().startsWith('appartement');
    const number = property.ademe_dpe_number;

    useEffect(() => {
        setSheet(null);
        if (!apartment || !number) return;
        const controller = new AbortController();
        setState('loading');
        (async () => {
            try {
                const res = await authedFetch(`/api/immeuble?dpe=${encodeURIComponent(number)}`, { signal: controller.signal });
                if (!res.ok) throw new Error();
                setSheet(await res.json());
                setState('idle');
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setState('error');
            }
        })();
        return () => controller.abort();
    }, [apartment, number, authedFetch]);

    if (!apartment || !number) return null;
    const copro = sheet?.copro;
    const labels = sheet ? (Object.entries(sheet.apartments.distribution) as [DPEClass, number][]).filter(([, c]) => c) : [];

    return (
        <Step n={n} title="L'immeuble" subtitle="La copropriété, ses obligations et les travaux collectifs à venir.">
            {state === 'loading' && !sheet && <Loader2 className="animate-spin text-faint" />}
            {state === 'error' && <p className="text-sm text-muted">La fiche de l'immeuble n'est pas disponible pour le moment.</p>}
            {sheet && (
                <div className="space-y-6">
                    <div className="flex items-start gap-3">
                        <Building2 size={20} className="mt-0.5 shrink-0 text-brass" />
                        {copro ? (
                            <div>
                                <p className="text-ink">{copro.name || `Copropriété n° ${copro.immat}`}</p>
                                <p className="text-xs text-faint">
                                    Registre national des copropriétés · n° {copro.immat}{copro.match === 'position' ? ' · rapprochée par l’adresse' : ''}{copro.match === 'corner' ? ` · immatriculée au ${copro.address || 'une autre adresse'} (immeuble d’angle probable, à vérifier)` : ''}
                                </p>
                            </div>
                        ) : (
                            <p className="text-sm text-muted">Adresse non retrouvée dans le registre national des copropriétés : la fiche repose sur les DPE publiés.</p>
                        )}
                    </div>

                    <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                        {copro?.lots_main != null && <Fact label="Lots principaux" value={`${copro.lots_main}${copro.lots_housing ? ` dont ${copro.lots_housing} logements` : ''}`} />}
                        {!!copro?.lots_parking && <Fact label="Stationnements" value={String(copro.lots_parking)} />}
                        {sheet.period && <Fact label="Construction" value={sheet.period} />}
                        {copro && <Fact label="Syndic" value={copro.syndic_name || (copro.syndic_type ? copro.syndic_type[0].toUpperCase() + copro.syndic_type.slice(1) : 'Non renseigné')} />}
                        {copro?.mandate_end && <Fact label="Fin du mandat du syndic" value={dateFr(copro.mandate_end)} />}
                        {(copro?.aided || copro?.in_pdp || copro?.qpv) && (
                            <Fact label="Dispositifs publics" value={[copro.aided && 'Copropriété aidée', copro.in_pdp && 'Plan de sauvegarde ou dispositif public', copro.qpv && `Quartier prioritaire (${copro.qpv})`].filter(Boolean).join(' · ')} />
                        )}
                    </dl>

                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="rounded-xl border border-line p-4">
                            <p className="text-xs text-faint">DPE de l'immeuble</p>
                            {sheet.building_dpe ? (
                                <div className="mt-2 flex items-center gap-3">
                                    <DpeBadge label={sheet.building_dpe.label} />
                                    <span className="text-sm text-muted">DPE collectif du {sheet.building_dpe.date_fr}</span>
                                </div>
                            ) : <p className="mt-2 text-sm text-muted">Aucun DPE collectif publié à cette adresse.</p>}
                        </div>
                        <div className="rounded-xl border border-line p-4">
                            <p className="text-xs text-faint">DPE des appartements publiés ({sheet.apartments.count})</p>
                            <div className="mt-2 flex flex-wrap gap-2">
                                {labels.map(([l, c]) => (
                                    <span key={l} className="flex items-center gap-1.5 text-sm text-ink-soft"><DpeBadge label={l} size="sm" />× {c}</span>
                                ))}
                            </div>
                            {sheet.dimensions.dwellings != null && sheet.apartments.count > sheet.dimensions.dwellings && (
                                <p className="mt-2 text-xs text-faint">
                                    Plus de DPE que de logements ({sheet.dimensions.dwellings}) : certains logements ont été diagnostiqués plusieurs fois,
                                    ou plusieurs bâtiments partagent cette adresse.
                                </p>
                            )}
                        </div>
                    </div>

                    {sheet.obligations.length > 0 && (
                        <div>
                            <p className="text-sm font-medium text-ink-soft">Obligations de la copropriété</p>
                            <ul className="mt-2 space-y-3">
                                {sheet.obligations.map(o => (
                                    <li key={o.id} className="flex gap-3 text-sm">
                                        {o.status === 'done'
                                            ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-sage" aria-label="Réalisé" />
                                            : <AlertTriangle size={16} className="mt-0.5 shrink-0 text-brass" aria-label="À vérifier" />}
                                        <span>
                                            <span className="text-ink">{o.title}</span>
                                            {o.since && o.status !== 'done' && <span className="text-faint"> · obligatoire depuis le {dateFr(o.since)}</span>}
                                            <span className="block text-muted">{o.detail}</span>
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {sheet.works.length === 0 && sheet.works_note && (
                        <div>
                            <p className="text-sm font-medium text-ink-soft">Travaux collectifs</p>
                            <p className="mt-1 text-sm text-muted">{sheet.works_note}</p>
                        </div>
                    )}

                    {sheet.works.length > 0 && sheet.total && (
                        <div>
                            <p className="text-sm font-medium text-ink-soft">Travaux collectifs probables</p>
                            <ul className="mt-1 divide-y divide-line/60">
                                {sheet.works.map(w => (
                                    <li key={w.id} className="py-2 flex flex-wrap items-baseline justify-between gap-x-4 text-sm">
                                        <span className="text-ink">{w.name} <span className="text-faint">· {w.reason}</span></span>
                                        <span className="text-ink-soft tabular-nums">{eurRange(w.low, w.high)}</span>
                                    </li>
                                ))}
                                <li className="py-2 flex justify-between text-sm font-medium"><span className="text-ink">Pour l'immeuble</span><span className="text-ink tabular-nums">{eurRange(...sheet.total)}</span></li>
                            </ul>
                            {sheet.estimate && (
                                <div className="mt-3 rounded-xl border border-brass/40 bg-brass/5 p-4">
                                    <p className="text-sm text-muted">Quote-part de cet appartement (environ {pct(sheet.estimate.share)} de la surface)</p>
                                    <p className="mt-1 text-xl text-ink tabular-nums">{eurRange(sheet.estimate.share_low, sheet.estimate.share_high)}</p>
                                    <p className="mt-1 text-sm text-muted">
                                        Environ {eurRange(sheet.estimate.net_low, sheet.estimate.net_high)} après MaPrimeRénov' Copropriété
                                        ({Math.round(sheet.estimate.aid_rates[0] * 100)} à {Math.round(sheet.estimate.aid_rates[1] * 100)} % des travaux si le gain énergétique atteint 35 %).
                                    </p>
                                </div>
                            )}
                            <p className="mt-3 text-xs text-faint">
                                Ordres de grandeur déduits du DPE {sheet.works_source === 'immeuble' ? "de l'immeuble" : "de l'appartement"}
                                {sheet.dimensions.surface ? ` (${num(sheet.dimensions.surface)} m² habitables, ${sheet.dimensions.levels} niveaux, ${sheet.dimensions.dwellings} logements)` : ''}.
                                Le montant réel dépend du plan pluriannuel de travaux voté en assemblée générale ; la répartition suit les tantièmes du règlement de copropriété.
                                Ces éléments figurent aussi dans le rapport PDF.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </Step>
    );
}
