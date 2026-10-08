import { useCallback, useEffect, useState } from 'react';
import { Loader2, Mail, Phone, Trash2 } from 'lucide-react';
import { useAccount } from '../account';
import { Link } from '../router';
import { Button, Card } from '../ui';
import { SiteFooter, SiteHeader } from './site';

export interface AgentPageData {
    agency_name?: string;
    agent_name?: string | null;
    phone?: string | null;
    email?: string | null;
}

interface Lead {
    id: string;
    name: string;
    phone: string | null;
    email: string | null;
    message: string | null;
    status: 'new' | 'contacted' | 'closed';
    created_at: string;
    consent_at: string;
    address: string | null;
    dpe_number: string | null;
}

interface LinkStat {
    code: string;
    address: string;
    label: string | null;
    created_at: string;
    visits: number;
    last_visit_at: string | null;
}

const STATUS = [
    { value: 'new', label: 'À rappeler' },
    { value: 'contacted', label: 'Contacté' },
    { value: 'closed', label: 'Clôturé' },
];

const fieldClass = 'w-full rounded-xl border border-line bg-raised px-3.5 h-11 text-ink outline-none focus:border-brass/70';
const date = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }) : '–');

export async function errorDetail(res: Response, fallback: string) {
    const body = await res.json().catch(() => ({}));
    if (Array.isArray(body.detail)) return 'Vérifiez le téléphone et l\'email saisis.';
    return body.detail || fallback;
}

// Agency shown on the owners' pages; reused by the letter dialog of the map
export function AgentPageForm({ initial, onSaved }: { initial: AgentPageData; onSaved: (p: AgentPageData) => void }) {
    const { authedFetch } = useAccount();
    const [form, setForm] = useState<AgentPageData>(initial);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    useEffect(() => setForm(initial), [initial]);

    const save = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        try {
            const res = await authedFetch('/api/agent-page', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agency_name: form.agency_name || '', agent_name: form.agent_name || null,
                    phone: form.phone || null, email: form.email || null }),
            });
            if (!res.ok) throw new Error(await errorDetail(res, "L'enregistrement a échoué."));
            const page = await res.json();
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
            onSaved(page);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <form onSubmit={save} className="grid sm:grid-cols-2 gap-3">
            <input className={fieldClass} placeholder="Nom de l'agence" required minLength={2} maxLength={80} aria-label="Nom de l'agence"
                value={form.agency_name || ''} onChange={e => setForm({ ...form, agency_name: e.target.value })} />
            <input className={fieldClass} placeholder="Votre nom (facultatif)" maxLength={80} aria-label="Votre nom"
                value={form.agent_name || ''} onChange={e => setForm({ ...form, agent_name: e.target.value })} />
            <input className={fieldClass} placeholder="Téléphone affiché" maxLength={25} inputMode="tel" aria-label="Téléphone"
                value={form.phone || ''} onChange={e => setForm({ ...form, phone: e.target.value })} />
            <input className={fieldClass} placeholder="Email affiché" type="email" maxLength={120} aria-label="Email"
                value={form.email || ''} onChange={e => setForm({ ...form, email: e.target.value })} />
            {error && <p className="sm:col-span-2 text-sm text-coral">{error}</p>}
            <div className="sm:col-span-2 flex items-center gap-3">
                <Button type="submit" disabled={saving} className="h-10">
                    {saving && <Loader2 size={14} className="animate-spin" />}Enregistrer
                </Button>
                {saved && <span className="text-sm text-sage">Enregistré</span>}
            </div>
        </form>
    );
}

export default function ContactsPage() {
    const { session, me, config, openLogin, startSubscription, authedFetch } = useAccount();
    const [page, setPage] = useState<AgentPageData>({});
    const [leads, setLeads] = useState<Lead[]>([]);
    const [links, setLinks] = useState<LinkStat[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!session) { setLoading(false); return; }
        setLoading(true);
        try {
            const [p, l] = await Promise.all([authedFetch('/api/agent-page'), authedFetch('/api/leads')]);
            if (p.ok) setPage(await p.json());
            if (l.ok) {
                const data = await l.json();
                setLeads(data.leads);
                setLinks(data.links);
            }
        } catch {
            setError('Le chargement a échoué.');
        } finally {
            setLoading(false);
        }
    }, [session, authedFetch]);

    useEffect(() => { load(); }, [load]);

    const setStatus = async (lead: Lead, status: string) => {
        const res = await authedFetch(`/api/leads/${lead.id}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
        });
        if (res.ok) setLeads(ls => ls.map(l => (l.id === lead.id ? { ...l, status: status as Lead['status'] } : l)));
    };

    const remove = async (lead: Lead) => {
        if (!window.confirm(`Supprimer définitivement la demande de ${lead.name} ?`)) return;
        const res = await authedFetch(`/api/leads/${lead.id}`, { method: 'DELETE' });
        if (res.ok) setLeads(ls => ls.filter(l => l.id !== lead.id));
    };

    const newCount = leads.filter(l => l.status === 'new').length;

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
                <div>
                    <h1 className="text-3xl sm:text-4xl text-ink">Contacts</h1>
                    <p className="mt-2 text-muted max-w-3xl">
                        Les propriétaires qui ont scanné le QR code de vos courriers et demandé à être rappelés. Ils ont donné leur accord
                        pour être recontactés par votre agence au sujet de leur logement.
                    </p>
                </div>

                {!session ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Connectez-vous pour voir vos contacts</p>
                        <Button className="mt-4" onClick={() => openLogin()} disabled={!config?.auth_enabled}>Se connecter</Button>
                    </Card>
                ) : me && !me.is_pro ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Réservé aux abonnés Pro</p>
                        <p className="mt-1 text-sm text-muted">Courriers avec QR code, pages de contact à vos couleurs et demandes de rappel des propriétaires.</p>
                        <Button className="mt-4" onClick={startSubscription}>Passer Pro</Button>
                    </Card>
                ) : loading ? (
                    <Loader2 className="animate-spin text-brass" />
                ) : (
                    <>
                        {error && <Card className="p-4 text-sm text-coral">{error}</Card>}

                        <Card className="p-5 sm:p-6">
                            <h2 className="text-xl text-ink">Demandes de rappel {newCount > 0 && <span className="ml-2 rounded-full bg-brass px-2 py-0.5 text-xs text-canvas">{newCount} à rappeler</span>}</h2>
                            {leads.length === 0 ? (
                                <p className="mt-3 text-sm text-muted">
                                    Aucune demande pour l'instant. Préparez des courriers avec QR code depuis la{' '}
                                    <Link to="/prospection" className="underline text-brass-light">carte de prospection</Link>.
                                </p>
                            ) : (
                                <ul className="mt-4 divide-y divide-line/70">
                                    {leads.map(l => (
                                        <li key={l.id} className="py-4 flex flex-col sm:flex-row sm:items-start gap-3 sm:justify-between">
                                            <div className="min-w-0">
                                                <p className="text-ink font-medium">{l.name}</p>
                                                <p className="text-sm text-muted">{l.address} · {date(l.created_at)}</p>
                                                <div className="mt-1 flex flex-wrap gap-4 text-sm">
                                                    {l.phone && <a href={`tel:${l.phone.replace(/[^0-9+]/g, '')}`} className="flex items-center gap-1.5 text-brass-light"><Phone size={14} />{l.phone}</a>}
                                                    {l.email && <a href={`mailto:${l.email}`} className="flex items-center gap-1.5 text-brass-light"><Mail size={14} />{l.email}</a>}
                                                </div>
                                                {l.message && <p className="mt-2 text-sm text-ink-soft whitespace-pre-line">« {l.message} »</p>}
                                                <p className="mt-1 text-xs text-faint">Consentement donné le {date(l.consent_at)}</p>
                                            </div>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <select value={l.status} onChange={e => setStatus(l, e.target.value)} aria-label="Statut"
                                                    className="h-9 rounded-lg border border-line bg-raised px-2 text-sm text-ink">
                                                    {STATUS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                                                </select>
                                                <button type="button" onClick={() => remove(l)} className="p-2 text-faint hover:text-coral" aria-label="Supprimer">
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )}
                            <p className="mt-4 text-xs text-faint">
                                Vous êtes responsable de ces données (CGV, article 14). Supprimez une demande dès qu'elle n'est plus utile, et au plus tard 3 ans après le dernier contact.
                            </p>
                        </Card>

                        <Card className="p-5 sm:p-6">
                            <h2 className="text-xl text-ink">Votre agence</h2>
                            <p className="mt-1 text-sm text-muted">Ces informations apparaissent sur la page que le propriétaire ouvre en scannant le QR code.</p>
                            <div className="mt-4"><AgentPageForm initial={page} onSaved={setPage} /></div>
                        </Card>

                        <Card className="p-5 sm:p-6">
                            <h2 className="text-xl text-ink">Courriers préparés</h2>
                            {links.length === 0 ? (
                                <p className="mt-3 text-sm text-muted">Aucun courrier préparé.</p>
                            ) : (
                                <div className="mt-3 overflow-x-auto">
                                    <table className="w-full text-sm min-w-[520px]">
                                        <thead><tr className="text-left text-faint"><th className="font-normal py-2">Adresse</th><th className="font-normal">Préparé le</th><th className="font-normal">Visites</th><th className="font-normal">Dernière visite</th></tr></thead>
                                        <tbody className="divide-y divide-line/70">
                                            {links.map(k => (
                                                <tr key={k.code}>
                                                    <td className="py-2 text-ink-soft">{k.address}</td>
                                                    <td className="text-muted">{date(k.created_at)}</td>
                                                    <td className="text-ink tabular-nums">{k.visits}</td>
                                                    <td className="text-muted">{date(k.last_visit_at)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    </>
                )}
            </main>
            <SiteFooter />
        </div>
    );
}
