import { useEffect, useState } from 'react';
import { Download, Loader2, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, DpeBadge, eur, eurRange, type DPEClass } from '../ui';
import { AgentPageForm, errorDetail, type AgentPageData } from './Contacts';

interface Range { value: number; low: number; high: number }

interface Valuation {
    current_label: DPEClass;
    target_label: DPEClass;
    value_now: Range;
    value_after: Range | null;
    price_m2_now: number;
    works: boolean;
    rest: { low: number; high: number; value: number };
    net_gain: number | null;
    market: { price_per_m2: number; q25: number; q75: number; sales: number; scope: string; period: string };
}

const fieldClass = 'w-full rounded-xl border border-line bg-raised px-3.5 h-11 text-ink outline-none focus:border-brass/70';

export default function ValuationDialog({ meta, simulation, onClose }: { meta: object; simulation: object; onClose: () => void }) {
    const { authedFetch } = useAccount();
    const [adjustment, setAdjustment] = useState(0);
    const [note, setNote] = useState('');
    const [client, setClient] = useState('');
    const [result, setResult] = useState<Valuation | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [downloading, setDownloading] = useState(false);
    const [needsAgency, setNeedsAgency] = useState(false);

    const body = () => JSON.stringify({ meta, simulation, adjustment_pct: adjustment, adjustment_note: note || null, client_name: client || null });

    // Recomputed when the adjustment changes (debounced)
    useEffect(() => {
        const timer = setTimeout(async () => {
            setLoading(true);
            try {
                const res = await authedFetch('/api/valuation', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body() });
                if (!res.ok) throw new Error(await errorDetail(res, "L'avis de valeur n'a pas pu être calculé."));
                setResult(await res.json());
                setError(null);
            } catch (e) {
                setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }, 350);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [adjustment]);

    const download = async () => {
        setDownloading(true);
        setError(null);
        try {
            const res = await authedFetch('/api/valuation/pdf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body() });
            if (res.status === 409) { setNeedsAgency(true); return; }
            if (!res.ok) throw new Error(await errorDetail(res, 'Le PDF n\'a pas pu être généré.'));
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = res.headers.get('content-disposition')?.match(/filename=([^;]+)/)?.[1] || 'Avis_de_valeur.pdf';
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setDownloading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[1000] bg-canvas/80 backdrop-blur-sm flex items-start sm:items-center justify-center p-4 overflow-y-auto" role="dialog" aria-modal="true">
            <Card className="w-full max-w-2xl p-5 sm:p-6 relative">
                <button type="button" onClick={onClose} className="absolute top-4 right-4 text-faint hover:text-ink" aria-label="Fermer"><X size={18} /></button>
                <h2 className="text-xl text-ink pr-8">Avis de valeur avant / après rénovation</h2>
                <p className="mt-1 text-sm text-muted">Ventes comparables (DVF) corrigées de la classe DPE, avec le scénario de travaux en cours.</p>

                {needsAgency ? (
                    <div className="mt-4">
                        <p className="text-sm text-muted mb-4">Renseignez votre agence : l'avis de valeur est édité à son nom.</p>
                        <AgentPageForm initial={{} as AgentPageData} onSaved={() => { setNeedsAgency(false); download(); }} />
                    </div>
                ) : (
                    <>
                        <div className="mt-5 min-h-[120px]">
                            {loading && !result ? (
                                <Loader2 className="animate-spin text-brass" />
                            ) : error && !result ? (
                                <p className="text-sm text-coral">{error}</p>
                            ) : result && (
                                <div className={`grid sm:grid-cols-3 gap-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
                                    <div className="rounded-xl bg-raised p-4">
                                        <p className="text-xs text-muted flex items-center gap-2">Valeur actuelle <DpeBadge label={result.current_label} size="sm" /></p>
                                        <p className="mt-1 font-serif text-2xl text-brass-light tabular-nums">{eur(result.value_now.value)}</p>
                                        <p className="text-xs text-faint tabular-nums">{eur(result.value_now.low)} à {eur(result.value_now.high)}</p>
                                    </div>
                                    {result.value_after ? (
                                        <>
                                            <div className="rounded-xl bg-raised p-4">
                                                <p className="text-xs text-muted flex items-center gap-2">Après travaux <DpeBadge label={result.target_label} size="sm" /></p>
                                                <p className="mt-1 font-serif text-2xl text-ink tabular-nums">{eur(result.value_after.value)}</p>
                                                <p className="text-xs text-faint tabular-nums">reste à charge {eurRange(result.rest.low, result.rest.high)}</p>
                                            </div>
                                            <div className="rounded-xl bg-raised p-4">
                                                <p className="text-xs text-muted">Plus-value nette des travaux</p>
                                                <p className={`mt-1 font-serif text-2xl tabular-nums ${(result.net_gain || 0) >= 0 ? 'text-sage' : 'text-coral'}`}>
                                                    {(result.net_gain || 0) >= 0 ? '+' : '−'} {eur(Math.abs(result.net_gain || 0))}
                                                </p>
                                                <p className="text-xs text-faint">valeur gagnée moins le reste à charge</p>
                                            </div>
                                        </>
                                    ) : (
                                        <p className="sm:col-span-2 text-sm text-muted self-center">Sélectionnez des travaux pour estimer la valeur après rénovation.</p>
                                    )}
                                    <p className="sm:col-span-3 text-xs text-faint">
                                        Marché : {eur(result.market.price_per_m2)}/m² médian ({eur(result.market.q25)} à {eur(result.market.q75)}),
                                        {' '}{result.market.sales} ventes {result.market.scope} ({result.market.period}). Pour ce bien : {eur(result.price_m2_now)}/m².
                                    </p>
                                </div>
                            )}
                        </div>

                        <div className="mt-5 grid sm:grid-cols-2 gap-3">
                            <label className="sm:col-span-2 text-sm text-ink-soft">
                                Ajustement du conseiller : <b className="text-ink tabular-nums">{adjustment > 0 ? '+' : ''}{adjustment} %</b>
                                <input type="range" min={-20} max={20} step={1} value={adjustment} onChange={e => setAdjustment(Number(e.target.value))}
                                    className="mt-2 w-full accent-[#C9A45C]" aria-label="Ajustement en pourcentage" />
                                <span className="block text-xs text-faint">État, étage, extérieur, stationnement, vue… par rapport aux ventes comparables.</span>
                            </label>
                            <input className={fieldClass} placeholder="Motif de l'ajustement (facultatif)" maxLength={300}
                                value={note} onChange={e => setNote(e.target.value)} aria-label="Motif de l'ajustement" />
                            <input className={fieldClass} placeholder="Établi pour (facultatif)" maxLength={100}
                                value={client} onChange={e => setClient(e.target.value)} aria-label="Client" />
                        </div>

                        {error && result && <p className="mt-3 text-sm text-coral">{error}</p>}
                        <Button onClick={download} disabled={downloading || !result} className="mt-5 w-full">
                            {downloading ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}Télécharger l'avis de valeur (PDF)
                        </Button>
                    </>
                )}
            </Card>
        </div>
    );
}
