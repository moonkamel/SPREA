import { useEffect, useMemo, useState } from 'react';
import { Copy, Loader2, Printer, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, errorDetail } from '../ui';
import type { AgentPageData } from './Contacts';

// « Connaître le propriétaire »: the request anyone can send to the land
// registry service or the town hall for the owner of a given property
// (article L107 A of the Livre des procédures fiscales), prefilled with the
// parcel's cadastral reference. SPREA never fetches nor stores the owner's name.

export interface OwnerTarget { address: string; lat: number; lon: number }
interface Parcel { insee: string | null; commune: string | null; section: string | null; numero: string | null; prefixe: string | null }

// Requests prepared this month, on this device: a reminder of the legal limit
const COUNT_KEY = 'sprea-owner-requests';
const MONTHLY_LIMIT = 10;
const thisMonth = () => new Date().toISOString().slice(0, 7);
function readCount(): number {
    try {
        const v = JSON.parse(localStorage.getItem(COUNT_KEY) || '{}');
        return v.month === thisMonth() ? v.count || 0 : 0;
    } catch { return 0; }
}
function bumpCount(): number {
    const n = readCount() + 1;
    try { localStorage.setItem(COUNT_KEY, JSON.stringify({ month: thisMonth(), count: n })); } catch { /* private mode */ }
    return n;
}

export function requestText(t: OwnerTarget, p: Parcel, agency: AgentPageData): string {
    const ref = [p.prefixe ? `préfixe ${p.prefixe}` : '', p.section ? `section ${p.section.replace(/^0+/, '')}` : '', p.numero ? `parcelle n° ${p.numero.replace(/^0+/, '')}` : '']
        .filter(Boolean).join(', ');
    const who = [agency.agent_name || '[Vos nom et prénom]', agency.agency_name, '[Votre adresse postale]'].filter(Boolean).join('\n');
    return `${who}

À l'attention du centre des impôts fonciers
(ou de la mairie de ${p.commune || '[commune]'})

Objet : demande de communication d'un extrait des informations cadastrales (article L107 A du Livre des procédures fiscales)

Madame, Monsieur,

Je vous prie de bien vouloir me communiquer l'identité et l'adresse du ou des propriétaires du bien suivant :

- Adresse : ${t.address}
- Commune : ${p.commune || '[commune]'}${p.insee ? ` (code INSEE ${p.insee})` : ''}
- Référence cadastrale : ${ref || '[section et numéro de parcelle]'}

Cette demande est ponctuelle et porte sur ce seul bien.

Je vous remercie par avance et vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

Fait le ${new Date().toLocaleDateString('fr-FR')}
${agency.agent_name || '[Signature]'}`;
}

export default function OwnerRequestDialog({ target, onClose }: { target: OwnerTarget; onClose: () => void }) {
    const { authedFetch } = useAccount();
    const [parcel, setParcel] = useState<Parcel | null>(null);
    const [agency, setAgency] = useState<AgentPageData>({});
    const [error, setError] = useState<string | null>(null);
    const [count, setCount] = useState(readCount);
    const [counted, setCounted] = useState(false);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {})).then(setAgency).catch(() => setAgency({}));
        authedFetch(`/api/parcel?lat=${target.lat}&lon=${target.lon}`).then(async r => {
            if (r.ok) setParcel(await r.json());
            else setError(await errorDetail(r, 'La parcelle n\'a pas pu être trouvée.'));
        }).catch(() => setError('La parcelle n\'a pas pu être trouvée.'));
    }, [authedFetch, target.lat, target.lon]);

    const [text, setText] = useState('');
    const prefilled = useMemo(() => (parcel ? requestText(target, parcel, agency) : ''), [parcel, agency, target]);
    useEffect(() => { if (prefilled) setText(prefilled); }, [prefilled]);

    // Counted once per dialog, when the request leaves it (copied or printed)
    const used = () => { if (!counted) { setCount(bumpCount()); setCounted(true); } };
    const copy = async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); used(); } catch { /* clipboard refused */ }
    };
    const print = () => {
        const w = window.open('', '_blank');
        if (!w) return;
        const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
        w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Demande au cadastre</title>
<style>body{font:12pt/1.5 Georgia,serif;margin:2.5cm;white-space:pre-wrap}</style></head><body>${esc(text)}</body></html>`);
        w.document.close();
        w.focus();
        w.print();
        used();
    };

    return (
        <div className="fixed inset-0 z-[1000] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="w-full max-w-2xl" onClick={e => e.stopPropagation()}>
                <Card className="max-h-[92vh] overflow-y-auto p-6 sm:p-7 relative">
                    <div role="dialog" aria-modal="true" aria-label="Connaître le propriétaire">
                        <button onClick={onClose} className="absolute top-5 right-5 text-faint hover:text-ink" aria-label="Fermer"><X size={20} /></button>
                        <h2 className="text-2xl text-ink pr-8">Connaître le propriétaire</h2>
                        <p className="mt-2 text-sm text-muted">
                            Toute personne peut demander au centre des impôts fonciers, ou en mairie, le nom et l'adresse du propriétaire
                            d'un bien précis (article L107 A du Livre des procédures fiscales). La demande est gratuite, ponctuelle,
                            et limitée à <b className="text-ink">5 par semaine et 10 par mois</b>.
                        </p>
                        <p className="mt-3 text-sm text-ink-soft">{target.address}</p>
                        {error && <p className="mt-4 text-sm text-coral">{error}</p>}
                        {!parcel && !error && <p className="mt-4 flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> Recherche de la parcelle au cadastre…</p>}
                        {parcel && (
                            <>
                                <div className="mt-4 grid grid-cols-3 gap-3">
                                    {[['Commune', `${parcel.commune || '–'}${parcel.insee ? ` (${parcel.insee})` : ''}`], ['Section', (parcel.section || '–').replace(/^0+/, '')], ['Parcelle', (parcel.numero || '–').replace(/^0+/, '')]].map(([k, v]) => (
                                        <div key={k} className="rounded-xl border border-line bg-raised px-3 py-2">
                                            <p className="text-[11px] uppercase tracking-[0.12em] text-faint">{k}</p>
                                            <p className="text-ink">{v}</p>
                                        </div>
                                    ))}
                                </div>
                                <p className="mt-4 text-xs uppercase tracking-[0.12em] text-faint">Votre demande, prête à envoyer</p>
                                <textarea value={text} onChange={e => setText(e.target.value)} rows={16} aria-label="Demande"
                                    className="mt-2 w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink font-mono leading-relaxed outline-none focus:border-brass/70" />
                                <div className="mt-3 flex flex-wrap items-center gap-3">
                                    <Button onClick={print} className="h-10"><Printer size={16} /> Imprimer</Button>
                                    <Button variant="secondary" onClick={copy} className="h-10"><Copy size={16} /> {copied ? 'Copié' : 'Copier le texte'}</Button>
                                    <span className={`text-xs ${count >= MONTHLY_LIMIT ? 'text-coral' : 'text-muted'}`}>
                                        {count} demande{count > 1 ? 's' : ''} préparée{count > 1 ? 's' : ''} ce mois-ci sur 10 autorisées
                                    </span>
                                </div>
                                <p className="mt-4 text-xs text-faint leading-relaxed">
                                    Envoyez-la au centre des impôts fonciers dont dépend la commune, ou déposez-la à la mairie. Complétez
                                    vos nom et adresse s'ils manquent : la demande doit indiquer l'identité du demandeur. Le nom obtenu sert
                                    à contacter ce propriétaire au sujet de ce bien ; il ne doit pas alimenter un fichier de prospection.
                                </p>
                            </>
                        )}
                    </div>
                </Card>
            </div>
        </div>
    );
}
