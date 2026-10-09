import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Loader2, Mail, Trash2, Users } from 'lucide-react';
import { Button, Card } from '../ui';
import { ROLE_NAMES, useAccount, type Team } from '../account';
import { navigate } from '../router';
import { PageShell } from './site';
import { useSeo } from '../seo';

interface Member { user_id: string; email: string | null; role: Team['role']; created_at: string }
interface Invitation { id: string; email: string; role: 'admin' | 'agent'; expires_at: string }
interface TeamData {
    team: Team | null;
    members?: Member[];
    invitations?: Invitation[];
    seats_used?: number;
    can_manage?: boolean;
    can_bill?: boolean;
}
interface Agency { id: string; name: string; seats: number; members: number; leads: number; leads_open: number }

const FIELD = 'h-11 px-3 rounded-xl bg-raised border border-line text-ink placeholder:text-faint outline-none focus:border-brass/70';

const errorDetail = async (res: Response) => {
    try { return (await res.json()).detail || `Erreur ${res.status}`; } catch { return `Erreur ${res.status}`; }
};

export default function TeamPage() {
    useSeo({ title: 'Équipe · SPREA', noindex: true });
    const { session, config, openLogin, authedFetch, refreshMe } = useAccount();
    const [data, setData] = useState<TeamData | null>(null);
    const [agencies, setAgencies] = useState<Agency[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [email, setEmail] = useState('');
    const [role, setRole] = useState<'agent' | 'admin'>('agent');
    const [busy, setBusy] = useState<string | null>(null);
    const [invited, setInvited] = useState<{ email: string; link: string; sent: boolean } | null>(null);
    const [copied, setCopied] = useState(false);
    const [seats, setSeats] = useState(0);

    const load = useCallback(async () => {
        const res = await authedFetch('/api/team');
        if (!res.ok) { setError(await errorDetail(res)); return; }
        const d: TeamData = await res.json();
        setData(d);
        if (d.team) setSeats(d.team.seats);
        if (d.team?.kind === 'reseau' && d.can_manage) {
            const n = await authedFetch('/api/team/network');
            if (n.ok) setAgencies((await n.json()).agencies);
        }
    }, [authedFetch]);

    useEffect(() => { if (session) load(); }, [session, load]);

    const run = async (key: string, fn: () => Promise<Response>, after?: (res: Response) => Promise<void>) => {
        setBusy(key);
        setError(null);
        try {
            const res = await fn();
            if (!res.ok) { setError(await errorDetail(res)); return; }
            if (after) await after(res);
            await load();
        } finally {
            setBusy(null);
        }
    };
    const json = (method: string, body?: object): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });

    if (!config?.auth_enabled) return <PageShell><p className="text-muted">Les comptes ne sont pas encore disponibles.</p></PageShell>;
    if (!session) {
        return (
            <PageShell>
                <Card className="max-w-lg mx-auto p-8 text-center">
                    <Users className="mx-auto text-brass" />
                    <p className="mt-4 text-ink">Connectez-vous pour voir votre équipe.</p>
                    <Button className="mt-6" onClick={() => openLogin()}>Se connecter</Button>
                </Card>
            </PageShell>
        );
    }
    if (!data) return <PageShell><Loader2 className="animate-spin text-faint mx-auto" /></PageShell>;

    if (!data.team) {
        return (
            <PageShell>
                <Card className="max-w-lg mx-auto p-8 text-center">
                    <Users className="mx-auto text-brass" />
                    <h1 className="mt-4 text-2xl text-ink">Équipez votre agence</h1>
                    <p className="mt-3 text-muted text-sm">Avec la formule Agence, chaque agent a son propre accès à SPREA, et vous suivez les demandes reçues par toute l'équipe. Si vous avez reçu une invitation, ouvrez le lien de l'email.</p>
                    <Button className="mt-6" onClick={() => navigate('/tarifs')}>Voir la formule Agence</Button>
                </Card>
            </PageShell>
        );
    }

    const { team } = data;
    const manage = !!data.can_manage;
    const full = (data.seats_used || 0) >= team.seats;

    return (
        <PageShell>
            <div className="space-y-6">
                <header>
                    <p className="text-sm text-brass tracking-wide">{team.kind === 'reseau' ? 'Réseau' : 'Agence'}{team.network ? ` · réseau ${team.network}` : ''}</p>
                    <h1 className="mt-2 text-4xl text-ink">{team.name}</h1>
                    <p className="mt-2 text-muted">
                        {ROLE_NAMES[team.role]} · {team.active ? 'abonnement actif' : 'abonnement inactif'} · {data.seats_used} / {team.seats} places utilisées
                    </p>
                </header>

                {error && <p role="alert" className="text-sm text-coral">{error}</p>}

                <Card className="p-6">
                    <h2 className="text-xl text-ink">Membres</h2>
                    <ul className="mt-4 divide-y divide-line/70">
                        {data.members!.map(m => (
                            <li key={m.user_id} className="py-3 flex flex-wrap items-center gap-3 justify-between">
                                <span className="min-w-0">
                                    <span className="block text-ink truncate">{m.email || 'Utilisateur'}</span>
                                    <span className="block text-xs text-faint">Depuis le {new Date(m.created_at).toLocaleDateString('fr-FR')}</span>
                                </span>
                                <span className="flex items-center gap-2">
                                    {team.role === 'owner' && m.role !== 'owner' ? (
                                        <select value={m.role} aria-label={`Rôle de ${m.email}`}
                                            onChange={e => run(`role-${m.user_id}`, () => authedFetch(`/api/team/members/${m.user_id}`, json('PATCH', { role: e.target.value })))}
                                            className="h-9 px-2 rounded-lg bg-raised border border-line text-sm text-ink">
                                            <option value="agent">Agent</option>
                                            <option value="admin">Responsable</option>
                                        </select>
                                    ) : (
                                        <span className="text-xs px-2 py-1 rounded-full border border-line text-ink-soft">{ROLE_NAMES[m.role]}</span>
                                    )}
                                    {manage && m.role !== 'owner' && (team.role === 'owner' || m.role === 'agent') && (
                                        <button aria-label={`Retirer ${m.email}`} className="p-2 text-faint hover:text-coral"
                                            onClick={() => window.confirm(`Retirer ${m.email} de l'équipe ? Ses demandes de rappel et ses courriers vous seront transférés.`)
                                                && run(`rm-${m.user_id}`, () => authedFetch(`/api/team/members/${m.user_id}`, { method: 'DELETE' }))}>
                                            <Trash2 size={16} />
                                        </button>
                                    )}
                                </span>
                            </li>
                        ))}
                    </ul>
                </Card>

                {manage && (
                    <Card className="p-6">
                        <h2 className="text-xl text-ink">Inviter un agent</h2>
                        <p className="mt-1 text-sm text-muted">L'agent reçoit un lien valable 7 jours et se connecte avec cette adresse email.</p>
                        <form className="mt-4 flex flex-col sm:flex-row gap-3"
                            onSubmit={e => {
                                e.preventDefault();
                                run('invite', () => authedFetch('/api/team/invitations', json('POST', { email, role })), async res => {
                                    const d = await res.json();
                                    setInvited({ email: d.invitation.email, link: d.link, sent: d.email_sent });
                                    setCopied(false);
                                    setEmail('');
                                });
                            }}>
                            <input type="email" required placeholder="agent@agence.fr" value={email} onChange={e => setEmail(e.target.value)} className={`${FIELD} flex-1`} aria-label="Email de l'agent" disabled={full} />
                            <select value={role} onChange={e => setRole(e.target.value as 'agent' | 'admin')} className={FIELD} aria-label="Rôle" disabled={full}>
                                <option value="agent">Agent</option>
                                <option value="admin">Responsable</option>
                            </select>
                            <Button type="submit" disabled={full || busy === 'invite'} className="h-11 sm:w-40">
                                {busy === 'invite' ? <Loader2 className="animate-spin" size={16} /> : <><Mail size={16} /> Inviter</>}
                            </Button>
                        </form>
                        {full && <p className="mt-3 text-sm text-brass-light">Toutes les places sont attribuées{data.can_bill ? ' : ajoutez une place ci-dessous.' : '.'}</p>}
                        {invited && (
                            <div className="mt-4 rounded-xl border border-line bg-raised p-4 text-sm">
                                <p className="text-ink-soft">{invited.sent ? `Invitation envoyée à ${invited.email}.` : `Envoyez ce lien à ${invited.email} :`}</p>
                                <div className="mt-2 flex gap-2 items-center">
                                    <code className="flex-1 min-w-0 truncate text-xs text-ink">{invited.link}</code>
                                    <button type="button" className="shrink-0 px-3 py-1.5 rounded-lg border border-line text-xs text-brass flex items-center gap-1"
                                        onClick={async () => { try { await navigator.clipboard.writeText(invited.link); setCopied(true); } catch { /* clipboard unavailable */ } }}>
                                        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'Copié' : 'Copier'}
                                    </button>
                                </div>
                            </div>
                        )}
                        {!!data.invitations?.length && (
                            <div className="mt-5">
                                <p className="text-sm text-ink-soft font-medium">Invitations en attente</p>
                                <ul className="mt-2 space-y-2">
                                    {data.invitations.map(i => (
                                        <li key={i.id} className="flex items-center justify-between gap-3 text-sm">
                                            <span className="text-ink-soft truncate">{i.email} <span className="text-faint">· {i.role === 'admin' ? 'responsable' : 'agent'} · expire le {new Date(i.expires_at).toLocaleDateString('fr-FR')}</span></span>
                                            <button className="text-faint hover:text-coral text-xs" onClick={() => run(`inv-${i.id}`, () => authedFetch(`/api/team/invitations/${i.id}`, { method: 'DELETE' }))}>Annuler</button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </Card>
                )}

                {data.can_bill && (
                    <Card className="p-6">
                        <h2 className="text-xl text-ink">Nombre de places</h2>
                        <p className="mt-1 text-sm text-muted">Facturé au prorata sur votre prochaine facture. Vous ne pouvez pas descendre sous le nombre de places utilisées.</p>
                        <form className="mt-4 flex items-center gap-3" onSubmit={e => { e.preventDefault(); run('seats', () => authedFetch('/api/team/seats', json('PUT', { seats }))); }}>
                            <input type="number" min={2} max={50} value={seats} onChange={e => setSeats(Number(e.target.value) || 0)} className={`${FIELD} w-24`} aria-label="Nombre de places" />
                            <Button type="submit" variant="secondary" disabled={seats === team.seats || busy === 'seats'} className="h-11">
                                {busy === 'seats' && <Loader2 className="animate-spin" size={16} />} Mettre à jour
                            </Button>
                        </form>
                    </Card>
                )}

                {agencies && (
                    <Card className="p-6">
                        <h2 className="text-xl text-ink">Agences du réseau</h2>
                        {agencies.length === 0 ? <p className="mt-3 text-sm text-faint">Aucune agence rattachée pour le moment : écrivez-nous pour en ajouter.</p> : (
                            <div className="mt-4 overflow-x-auto">
                                <table className="w-full text-sm min-w-[480px]">
                                    <thead><tr className="text-left text-faint">
                                        <th className="py-2 font-normal">Agence</th><th className="py-2 font-normal text-right">Agents</th>
                                        <th className="py-2 font-normal text-right">Demandes reçues</th><th className="py-2 font-normal text-right">À rappeler</th>
                                    </tr></thead>
                                    <tbody className="divide-y divide-line/70">
                                        {agencies.map(a => (
                                            <tr key={a.id}>
                                                <td className="py-2.5 text-ink">{a.name}</td>
                                                <td className="py-2.5 text-right tabular-nums text-ink-soft">{a.members} / {a.seats}</td>
                                                <td className="py-2.5 text-right tabular-nums text-ink-soft">{a.leads}</td>
                                                <td className="py-2.5 text-right tabular-nums text-ink-soft">{a.leads_open}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                        <p className="mt-3 text-xs text-faint">Le réseau voit les chiffres de ses agences, pas les coordonnées des propriétaires : chaque agence reste responsable de ses contacts.</p>
                    </Card>
                )}

                {team.role !== 'owner' && (
                    <button className="text-sm text-faint hover:text-coral"
                        onClick={() => window.confirm(`Quitter ${team.name} ? Vous perdrez l'accès à SPREA fourni par l'agence ; vos demandes de rappel restent à l'agence.`)
                            && run('leave', () => authedFetch('/api/team/leave', { method: 'POST' }), async () => { await refreshMe(); navigate('/'); })}>
                        Quitter l'équipe
                    </button>
                )}
            </div>
        </PageShell>
    );
}
