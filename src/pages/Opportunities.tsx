import { useState } from 'react';
import { Download, FileText, Loader2, TrendingUp, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, DpeBadge, errorDetail, eur, type DPEClass } from '../ui';

export type InvestorProfile = 'marchand' | 'bailleur';

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
    aids: number;
    total: number;
    resale: number;
    margin: number;
    margin_pct: number | null;
    rent_month?: number;
    gross_yield?: number | null;
    rental_now: string;
    rental_after: string;
    risks: string[];
}

export interface OpportunityScan {
    profile: InvestorProfile;
    items: Opportunity[];
    analysed: number;
    valued: number;
    positive: number;
    total: number;
    best_margin: number | null;
}

export const PROFILE_LABELS: Record<InvestorProfile, string> = {
    marchand: 'Marchand de biens (achat, travaux, revente)',
    bailleur: 'Investisseur bailleur (achat, travaux, location)',
};

export const BUDGETS = [
    { value: '', label: 'Tous budgets' },
    { value: '150000', label: 'Budget total ≤ 150 000 €' },
    { value: '250000', label: 'Budget total ≤ 250 000 €' },
    { value: '400000', label: 'Budget total ≤ 400 000 €' },
];

const pct = (v?: number | null) => (v == null ? '–' : `${v.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`);

// Marker colour: margin of the operation
export function marginColor(o: Opportunity): string {
    if (o.margin <= 0) return '#C4553A';
    if ((o.margin_pct ?? 0) >= 15) return '#3E8E63';
    return '#C9A45C';
}

export function OpportunityList({ scan, onFocus, onDossier }: {
    scan: OpportunityScan; onFocus: (o: Opportunity) => void; onDossier: (o: Opportunity) => void;
}) {
    const bailleur = scan.profile === 'bailleur';
    return (
        <Card className="p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-line">
                <p className="text-sm text-ink font-medium flex items-center gap-2"><TrendingUp size={15} className="text-brass" />
                    {scan.positive.toLocaleString('fr-FR')} opération{scan.positive > 1 ? 's' : ''} avec marge sur {scan.valued.toLocaleString('fr-FR')} chiffrée{scan.valued > 1 ? 's' : ''}
                </p>
                <p className="text-xs text-faint">
                    {scan.analysed} DPE récents analysés · classées par {bailleur ? 'rendement brut' : 'marge brute'} · estimations avant frais financiers et impôts
                </p>
            </div>
            {!scan.items.length ? (
                <p className="px-4 py-6 text-sm text-muted">Aucun logement chiffrable dans cette zone : élargissez les classes DPE ou déplacez la carte.</p>
            ) : (
                <ol className="max-h-[60vh] overflow-y-auto divide-y divide-line/70">
                    {scan.items.map((o, i) => (
                        <li key={o.number} className="px-4 py-3">
                            <button type="button" onClick={() => onFocus(o)} className="flex items-start gap-3 text-left w-full">
                                <span className="w-5 shrink-0 text-xs text-faint tabular-nums pt-1">{i + 1}</span>
                                <DpeBadge label={o.label} size="sm" />
                                <span className="min-w-0 flex-1">
                                    <span className="block text-sm text-ink truncate">{o.address}</span>
                                    <span className="block text-xs text-faint">
                                        {o.kind} · {Math.round(o.surface)} m² · {o.label} → {o.new_label} · achat ≈ {eur(o.price)}
                                    </span>
                                </span>
                                <span className="text-right shrink-0">
                                    <span className={`block text-sm font-medium tabular-nums ${o.margin > 0 ? 'text-sage' : 'text-coral'}`}>
                                        {o.margin > 0 ? '+' : '−'} {eur(Math.abs(o.margin))}
                                    </span>
                                    <span className="block text-[11px] text-faint tabular-nums">
                                        {bailleur && o.gross_yield != null ? `${pct(o.gross_yield)} brut` : pct(o.margin_pct)}
                                    </span>
                                </span>
                            </button>
                            <div className="mt-2 ml-8 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                                <span className="text-muted tabular-nums">budget {eur(o.total)} · revente ≈ {eur(o.resale)}{o.rent_month ? ` · loyer ≈ ${eur(o.rent_month)}/mois` : ''}</span>
                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1" onClick={() => onDossier(o)}>
                                    <FileText size={12} />Dossier d'investissement
                                </button>
                            </div>
                        </li>
                    ))}
                </ol>
            )}
        </Card>
    );
}

const fieldClass = 'w-full rounded-xl border border-line bg-raised px-3.5 h-11 text-ink outline-none focus:border-brass/70';

export function DossierDialog({ opportunity, profile, onClose }: { opportunity: Opportunity; profile: InvestorProfile; onClose: () => void }) {
    const { authedFetch } = useAccount();
    const [client, setClient] = useState('');
    const [price, setPrice] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const o = opportunity;

    const download = async () => {
        setBusy(true);
        setError(null);
        try {
            const asked = Number(price.replace(/\s/g, ''));
            const res = await authedFetch('/api/opportunities/dossier', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ number: o.number, profile, client_name: client || null, purchase_price: asked > 0 ? asked : null }),
            });
            if (!res.ok) throw new Error(await errorDetail(res, "Le dossier n'a pas pu être généré."));
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = res.headers.get('content-disposition')?.match(/filename=([^;]+)/)?.[1] || 'Dossier_investissement.pdf';
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[1000] bg-canvas/80 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto" role="dialog" aria-modal="true">
            <Card className="w-full max-w-xl p-5 sm:p-6 relative my-auto">
                <button type="button" onClick={onClose} className="absolute top-4 right-4 text-faint hover:text-ink" aria-label="Fermer"><X size={18} /></button>
                <h2 className="text-xl text-ink pr-8">Dossier d'investissement</h2>
                <p className="mt-1 text-sm text-muted">{o.address} · {o.kind} {Math.round(o.surface)} m² · {PROFILE_LABELS[profile]}</p>

                <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[['Achat estimé', eur(o.price)], ['Budget total', eur(o.total)], ['Après travaux', eur(o.resale)],
                        ['Marge brute', `${o.margin > 0 ? '+' : '−'} ${eur(Math.abs(o.margin))}`]].map(([k, v]) => (
                        <div key={k} className="rounded-xl bg-raised p-3">
                            <p className="text-[11px] text-muted">{k}</p>
                            <p className={`mt-0.5 text-sm font-medium tabular-nums ${k === 'Marge brute' ? (o.margin > 0 ? 'text-sage' : 'text-coral') : 'text-ink'}`}>{v}</p>
                        </div>
                    ))}
                </div>
                <p className="mt-3 text-xs text-faint">
                    Programme : {o.works_names.join(', ')} ({o.label} → {o.new_label}).
                    {o.rent_month ? ` Loyer de marché ≈ ${eur(o.rent_month)} / mois, ${pct(o.gross_yield)} brut.` : ''}
                </p>
                {o.risks.length > 0 && (
                    <ul className="mt-2 text-xs text-muted list-disc pl-4 space-y-0.5">{o.risks.map(r => <li key={r}>{r}</li>)}</ul>
                )}

                <div className="mt-4 grid sm:grid-cols-2 gap-3">
                    <input className={fieldClass} inputMode="numeric" placeholder="Prix demandé (facultatif)" value={price}
                        onChange={e => setPrice(e.target.value)} aria-label="Prix demandé" />
                    <input className={fieldClass} placeholder="Établi pour (facultatif)" maxLength={100}
                        value={client} onChange={e => setClient(e.target.value)} aria-label="Client" />
                </div>
                <p className="mt-1 text-xs text-faint">Avec le prix affiché de l'annonce, le dossier recalcule budget, marge et rendement.</p>

                {error && <p className="mt-3 text-sm text-coral">{error}</p>}
                <Button onClick={download} disabled={busy} className="mt-5 w-full">
                    {busy ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                    {busy ? 'Rédaction du dossier…' : 'Télécharger le dossier (PDF)'}
                </Button>
                <p className="mt-2 text-[11px] text-faint">Analyse rédigée avec l'IA à partir des seuls chiffres du dossier, à relire avant envoi.</p>
            </Card>
        </div>
    );
}
