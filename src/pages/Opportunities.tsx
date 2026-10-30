import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, Download, FileText, Loader2, TrendingUp, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, DpeBadge, errorDetail, eur, type DPEClass } from '../ui';

export type InvestorProfile = 'marchand' | 'bailleur';
// Who reads the file: the buyer of a dwelling the agency sells, or the owner it prospects
export type Audience = 'acheteur' | 'proprietaire';

export interface Opportunity {
    number: string;
    address: string;
    lat: number;
    lon: number;
    city: string | null;
    kind: string;
    surface: number;
    period: string | null;
    dpe_date: string | null;
    label: DPEClass;
    new_label: DPEClass;
    works_names: string[];
    price: number;
    notary: number;
    works: number;
    works_low: number;
    works_high: number;
    aids: number;
    total: number;
    resale: number;
    margin: number;
    margin_pct: number | null;
    // What the works add to the value, aids deducted (the potential)
    value_created: number;
    rent_month?: number;
    gross_yield?: number | null;
    rental_now: string;
    rental_after: string;
    risks: string[];
}

export type SortKey = 'potentiel' | 'recent' | 'valeur';

export interface OpportunityScan {
    profile: InvestorProfile;
    sort: SortKey;
    items: Opportunity[];
    analysed: number;
    valued: number;
    positive: number;
    total: number;
    best_margin: number | null;
}

// Follow-up of each address, shared by the agency
export type FollowUp = 'courrier' | 'relance' | 'rendez_vous' | 'mandat' | 'ecarte';

export const FOLLOW_UPS: { value: FollowUp | ''; label: string }[] = [
    { value: '', label: 'À contacter' },
    { value: 'courrier', label: 'Courrier envoyé' },
    { value: 'relance', label: 'Relancé' },
    { value: 'rendez_vous', label: 'Rendez-vous' },
    { value: 'mandat', label: 'Mandat signé' },
    { value: 'ecarte', label: 'Pas intéressé' },
];

export const SORTS: { value: SortKey; label: string }[] = [
    { value: 'potentiel', label: 'Plus fort potentiel' },
    { value: 'recent', label: 'DPE les plus récents' },
    { value: 'valeur', label: 'Valeur la plus élevée' },
];

export const FRESHNESS = [
    { value: '', label: 'Tous les DPE récents' },
    { value: '3', label: 'DPE de moins de 3 mois' },
    { value: '6', label: 'DPE de moins de 6 mois' },
    { value: '12', label: 'DPE de moins d\'un an' },
];

export const VALUES = [
    { value: '', label: 'Toutes valeurs' },
    { value: '150000', label: 'Valeur ≤ 150 000 €' },
    { value: '250000', label: 'Valeur ≤ 250 000 €' },
    { value: '400000', label: 'Valeur ≤ 400 000 €' },
];

export const PROFILE_LABELS: Record<InvestorProfile, string> = {
    bailleur: 'Acquéreur particulier (frais de notaire 8 %, aides comptées)',
    marchand: 'Marchand de biens (frais de notaire 3 %, sans aides)',
};

// "DPE de 3 mois", from the DPE date
export function dpeAge(day: string | null): string {
    if (!day) return 'DPE non daté';
    const d = new Date(day);
    const now = new Date();
    const months = (now.getFullYear() - d.getFullYear()) * 12 + now.getMonth() - d.getMonth();
    if (months < 1) return 'DPE de ce mois-ci';
    if (months < 12) return `DPE de ${months} mois`;
    const years = Math.floor(months / 12);
    return `DPE de ${years} an${years > 1 ? 's' : ''}`;
}

// Marker colour: what the renovation adds to the dwelling
export function potentialColor(o: Opportunity): string {
    if ((o.value_created ?? 0) <= 0) return '#8A93A3';
    if ((o.value_created ?? 0) >= 0.05 * o.price) return '#3E8E63';
    return '#C9A45C';
}

// With `detail`, a click opens the dwelling in place (the selected one), with
// everything the agent needs about it; without it, the list stays compact
export function OpportunityList({ scan, statuses, onStatus, onFocus, onDossier, selected, onSelect, detail }: {
    scan: OpportunityScan; statuses: Record<string, FollowUp>; onStatus: (o: Opportunity, s: FollowUp | '') => void;
    onFocus: (o: Opportunity) => void; onDossier: (o: Opportunity) => void;
    selected?: string | null; onSelect?: (o: Opportunity | null) => void; detail?: (o: Opportunity) => ReactNode;
}) {
    const items = useRef(new Map<string, HTMLLIElement>());
    // Selected from the map: brought into view in the list
    useEffect(() => {
        // Only the list scrolls, not the page
        const el = selected ? items.current.get(selected) : null;
        const list = el?.parentElement;
        if (!el || !list) return;
        const top = el.offsetTop - list.offsetTop;
        if (top < list.scrollTop || top + 60 > list.scrollTop + list.clientHeight) list.scrollTo({ top: Math.max(0, top - 8), behavior: 'smooth' });
    }, [selected]);
    const sortLabel = SORTS.find(s => s.value === scan.sort)?.label.toLowerCase() || 'plus fort potentiel';
    return (
        <Card className="p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-line" data-tour="invest-list">
                <p className="text-sm text-ink font-medium flex items-center gap-2"><TrendingUp size={15} className="text-brass" />
                    {scan.positive.toLocaleString('fr-FR')} bien{scan.positive > 1 ? 's' : ''} à fort potentiel
                </p>
                <p className="text-xs text-faint">
                    {scan.analysed} DPE récents analysés · {sortLabel} d'abord · valeurs estimées sur les ventes DVF
                </p>
            </div>
            {!scan.items.length ? (
                <p className="px-4 py-6 text-sm text-muted">Aucun logement chiffrable dans cette zone : élargissez les classes DPE ou déplacez la carte.</p>
            ) : (
                <ol className="max-h-[60vh] overflow-y-auto divide-y divide-line/70">
                    {scan.items.map((o, i) => {
                        const open = !!detail && selected === o.number;
                        return (
                        <li key={o.number} ref={el => { if (el) items.current.set(o.number, el); else items.current.delete(o.number); }}
                            className={`px-4 py-3 transition-colors ${open ? 'bg-raised/70' : ''}`}>
                            <button type="button" aria-expanded={detail ? open : undefined}
                                onClick={() => { onFocus(o); onSelect?.(open ? null : o); }} className="flex items-start gap-3 text-left w-full">
                                <span className="w-5 shrink-0 text-xs text-faint tabular-nums pt-1">{i + 1}</span>
                                <DpeBadge label={o.label} size="sm" />
                                <span className="min-w-0 flex-1">
                                    <span className="block text-sm text-ink truncate">{o.address}</span>
                                    <span className="block text-xs text-faint">
                                        {o.kind} · {Math.round(o.surface)} m² · {o.label} → {o.new_label} après travaux
                                    </span>
                                </span>
                                <span className="text-right shrink-0">
                                    <span className="block text-sm font-medium text-ink tabular-nums">≈ {eur(o.price)}</span>
                                    <span className="block text-[11px] text-faint">{dpeAge(o.dpe_date)}</span>
                                </span>
                                {detail && <ChevronDown size={14} className={`mt-1 shrink-0 text-faint transition-transform ${open ? 'rotate-180' : ''}`} />}
                            </button>
                            {open && detail!(o)}
                            <div className="mt-2 ml-8 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
                                <select value={statuses[o.number] || ''} onChange={e => onStatus(o, e.target.value as FollowUp | '')}
                                    aria-label={`Suivi de ${o.address}`} data-tour={i === 0 ? 'invest-status' : undefined}
                                    className={`h-7 rounded-lg border px-2 bg-raised ${statuses[o.number] ? 'border-brass/60 text-ink' : 'border-line text-muted'}`}>
                                    {FOLLOW_UPS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                                </select>
                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1" onClick={() => onDossier(o)}>
                                    <FileText size={12} />Dossier propriétaire
                                </button>
                                {detail && !open && (
                                    <button type="button" className="text-muted hover:text-ink" onClick={() => { onFocus(o); onSelect?.(o); }}>
                                        Tout voir
                                    </button>
                                )}
                            </div>
                        </li>
                        );
                    })}
                </ol>
            )}
        </Card>
    );
}

const fieldClass = 'w-full rounded-xl border border-line bg-raised px-3.5 h-11 text-ink outline-none focus:border-brass/70';

// Figures shown before downloading: what the dialog knows already
export interface DossierPreview {
    address: string;
    kind: string;
    surface: number;
    label: DPEClass;
    new_label: DPEClass;
    works_names: string[];
    price?: number;
    works?: number;
    aids?: number;
    resale?: number;
    rent_month?: number;
    risks?: string[];
}

const TEXTS: Record<Audience, { title: string; intro: string; price: string; priceHelp: string; client: string; aiNote: string }> = {
    proprietaire: {
        title: 'Dossier propriétaire',
        intro: "Le support de votre premier rendez-vous : ce que vaut le bien aujourd'hui, ce que les travaux changeraient, et comment le vendre malgré son DPE.",
        price: 'Prix envisagé (facultatif)',
        priceHelp: 'Sans prix, le dossier part de la valeur estimée sur les ventes comparables.',
        client: 'Propriétaire (facultatif)',
        aiNote: "Note rédigée avec l'IA à partir des seuls chiffres du dossier, à relire avant de la remettre.",
    },
    acheteur: {
        title: 'Dossier acheteur',
        intro: 'Partagez-le avec vos acquéreurs : ils ne voient plus une passoire, mais un projet chiffré.',
        price: 'Prix du mandat',
        priceHelp: 'Le dossier calcule budget, valeur après travaux et rendement à partir de ce prix.',
        client: 'Acquéreur (facultatif)',
        aiNote: "Note rédigée avec l'IA à partir des seuls chiffres du dossier, sans argument contre le prix, à relire avant envoi.",
    },
};

// The file of one dwelling, for its buyer or its owner. The request body says
// where the figures come from: a dwelling of the map (its DPE number) or the
// simulator (the works the agent chose).
export function DossierDialog({ preview, audience, request, onClose }: {
    preview: DossierPreview; audience: Audience;
    request: { url: string; body: Record<string, unknown> }; onClose: () => void;
}) {
    const { authedFetch } = useAccount();
    const [client, setClient] = useState('');
    const [price, setPrice] = useState('');
    const [profile, setProfile] = useState<InvestorProfile>('bailleur');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const t = TEXTS[audience];
    const o = preview;

    const download = async () => {
        setBusy(true);
        setError(null);
        try {
            const asked = Number(price.replace(/[\s €]/g, ''));
            const res = await authedFetch(request.url, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...request.body, audience, profile, client_name: client || null, purchase_price: asked > 0 ? asked : null }),
            });
            if (!res.ok) throw new Error(await errorDetail(res, "Le dossier n'a pas pu être généré."));
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = res.headers.get('content-disposition')?.match(/filename=([^;]+)/)?.[1] || `${t.title.replace(' ', '_')}.pdf`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const kpis = [
        o.price != null ? ['Valeur estimée', eur(o.price)] : null,
        o.works != null ? ['Travaux', eur(o.works)] : null,
        o.aids ? ['Aides estimées', `− ${eur(o.aids)}`] : null,
        o.resale != null ? ['Après travaux', eur(o.resale)] : null,
    ].filter(Boolean) as string[][];

    return (
        <div className="fixed inset-0 z-[1000] bg-canvas/80 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto" role="dialog" aria-modal="true">
            <Card className="w-full max-w-xl p-5 sm:p-6 relative my-auto">
                <button type="button" onClick={onClose} className="absolute top-4 right-4 text-faint hover:text-ink" aria-label="Fermer"><X size={18} /></button>
                <h2 className="text-xl text-ink pr-8">{t.title}</h2>
                <p className="mt-1 text-sm text-muted">{o.address} · {o.kind} {Math.round(o.surface)} m²</p>
                <p className="mt-2 text-sm text-ink-soft">{t.intro}</p>

                {kpis.length > 0 && (
                    <div className={`mt-4 grid grid-cols-2 ${kpis.length === 4 ? 'sm:grid-cols-4' : 'sm:grid-cols-3'} gap-2`}>
                        {kpis.map(([k, v]) => (
                            <div key={k} className="rounded-xl bg-raised p-3">
                                <p className="text-[11px] text-muted">{k}</p>
                                <p className={`mt-0.5 text-sm font-medium tabular-nums ${k === 'Aides estimées' ? 'text-sage' : 'text-ink'}`}>{v}</p>
                            </div>
                        ))}
                    </div>
                )}
                {(o.works_names.length > 0 || !!o.rent_month) && (
                    <p className="mt-3 text-xs text-faint">
                        {o.works_names.length > 0 && `Programme : ${o.works_names.join(', ')} (${o.label} → ${o.new_label}).`}
                        {o.rent_month ? ` Loyer de marché ≈ ${eur(o.rent_month)} / mois.` : ''}
                    </p>
                )}
                {!!o.risks?.length && (
                    <ul className="mt-2 text-xs text-muted list-disc pl-4 space-y-0.5">{o.risks.map(r => <li key={r}>{r}</li>)}</ul>
                )}

                <div className="mt-4 grid sm:grid-cols-2 gap-3">
                    <input className={fieldClass} inputMode="numeric" placeholder={t.price} value={price}
                        onChange={e => setPrice(e.target.value)} aria-label={t.price} data-tour="dossier-price" />
                    <input className={fieldClass} placeholder={t.client} maxLength={100}
                        value={client} onChange={e => setClient(e.target.value)} aria-label={t.client} />
                </div>
                <p className="mt-1 text-xs text-faint">{t.priceHelp}</p>
                <select value={profile} onChange={e => setProfile(e.target.value as InvestorProfile)} aria-label="Type d'acquéreur"
                    className="mt-3 h-10 w-full rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                    {(Object.keys(PROFILE_LABELS) as InvestorProfile[]).map(p => <option key={p} value={p}>{PROFILE_LABELS[p]}</option>)}
                </select>

                {error && <p className="mt-3 text-sm text-coral">{error}</p>}
                <Button onClick={download} disabled={busy} className="mt-5 w-full">
                    {busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                    {busy ? 'Rédaction du dossier…' : `Télécharger le ${t.title.toLowerCase()} (PDF)`}
                </Button>
                <p className="mt-2 text-[11px] text-faint">{t.aiNote} Estimations indicatives, à confirmer par devis.</p>
            </Card>
        </div>
    );
}
