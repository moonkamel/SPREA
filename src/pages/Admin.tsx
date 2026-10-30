import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, Loader2, Mail, MapPin, Phone, RefreshCw } from 'lucide-react';
import { useAccount } from '../account';
import { useSeo } from '../seo';
import { Button, Card } from '../ui';
import { SiteFooter, SiteHeader } from './site';

// Every request left on the public estimator, for SPREA's own team
interface AdminLead {
    id: string; created_at: string; consent_at: string; status: 'new' | 'contacted' | 'closed';
    name: string; phone?: string | null; email?: string | null;
    address: string; postcode?: string | null; city?: string | null; lat?: number | null; lon?: number | null;
    kind: 'appartement' | 'maison'; surface: number; value?: number | null; low?: number | null; high?: number | null;
    project: string; source?: string | null; advisor?: string | null;
    details?: { rooms?: number | null; dpe?: string | null; condition?: string; floor?: number | null };
}

const PROJECTS: Record<string, string> = { vendre_3m: 'Vendre sous 3 mois', vendre_12m: "Vendre dans l'année", reflexion: 'En réflexion', curiosite: 'Simple curiosité' };
const STATUS = [
    { value: 'new', label: 'À traiter' },
    { value: 'contacted', label: 'Contacté / transmis' },
    { value: 'closed', label: 'Clôturé' },
];
const CONDITIONS: Record<string, string> = { a_renover: 'à rénover', rafraichir: 'à rafraîchir', bon: 'bon état', refait: 'refait à neuf' };
const euros = (n?: number | null) => (n ? `${n.toLocaleString('fr-FR')} €` : '–');
const when = (iso: string) => new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const REFRESH_MS = 60_000;

function toCsv(leads: AdminLead[]) {
    const cols: [string, (l: AdminLead) => unknown][] = [
        ['date', l => l.created_at], ['statut', l => l.status], ['projet', l => PROJECTS[l.project] || l.project],
        ['nom', l => l.name], ['telephone', l => l.phone], ['email', l => l.email], ['adresse', l => l.address],
        ['code_postal', l => l.postcode], ['ville', l => l.city], ['type', l => l.kind], ['surface', l => l.surface],
        ['pieces', l => l.details?.rooms], ['dpe', l => l.details?.dpe], ['estimation', l => l.value], ['basse', l => l.low],
        ['haute', l => l.high], ['conseiller', l => l.advisor], ['source', l => l.source], ['consentement', l => l.consent_at],
    ];
    const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    return [cols.map(([k]) => k).join(';'), ...leads.map(l => cols.map(([, f]) => cell(f(l))).join(';'))].join('\n');
}

export default function AdminPage() {
    const { session, me, authedFetch, openLogin } = useAccount();
    useSeo({ title: 'Admin · SPREA', noindex: true });
    const [leads, setLeads] = useState<AdminLead[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
    const [status, setStatus] = useState<'all' | AdminLead['status']>('all');
    const [routing, setRouting] = useState<'all' | 'assigned' | 'unassigned'>('all');
    const [query, setQuery] = useState('');
    // Requests that arrived while the page was open
    const [fresh, setFresh] = useState<Set<string>>(new Set());

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await authedFetch('/api/admin/estimate-leads');
            if (res.status === 403) { setError("Ce compte n'a pas l'accès administrateur."); return; }
            if (!res.ok) throw new Error(String(res.status));
            const next: AdminLead[] = (await res.json()).leads;
            setLeads(prev => {
                if (prev) {
                    const known = new Set(prev.map(l => l.id));
                    const added = next.filter(l => !known.has(l.id)).map(l => l.id);
                    if (added.length) setFresh(f => new Set([...f, ...added]));
                }
                return next;
            });
            setError(null);
            setUpdatedAt(new Date());
        } catch {
            setError('Le chargement a échoué.');
        } finally {
            setLoading(false);
        }
    }, [authedFetch]);

    useEffect(() => {
        if (!session || !me?.is_admin) return;
        load();
        const timer = setInterval(load, REFRESH_MS);
        return () => clearInterval(timer);
    }, [session, me?.is_admin, load]);

    const update = async (lead: AdminLead, value: string) => {
        const res = await authedFetch(`/api/admin/estimate-leads/${lead.id}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: value }),
        });
        if (res.ok) setLeads(ls => ls && ls.map(l => (l.id === lead.id ? { ...l, status: value as AdminLead['status'] } : l)));
    };

    const shown = useMemo(() => {
        const q = query.trim().toLowerCase();
        return (leads || []).filter(l => (status === 'all' || l.status === status)
            && (routing === 'all' || (routing === 'assigned') === !!l.advisor)
            && (!q || [l.name, l.city, l.postcode, l.address, l.email, l.phone].some(v => v?.toLowerCase().includes(q))));
    }, [leads, status, routing, query]);

    const kpis = useMemo(() => {
        const all = leads || [];
        const week = Date.now() - 7 * 86_400_000;
        return [
            ['Demandes', all.length],
            ['À traiter', all.filter(l => l.status === 'new').length],
            ['7 derniers jours', all.filter(l => new Date(l.created_at).getTime() >= week).length],
            ['Sans conseiller', all.filter(l => !l.advisor).length],
            ['Vendre sous 3 mois', all.filter(l => l.project === 'vendre_3m').length],
        ] as [string, number][];
    }, [leads]);

    const download = () => {
        const blob = new Blob(['﻿' + toCsv(shown)], { type: 'text/csv;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `demandes-estimation-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    };

    const select = 'h-9 rounded-lg border border-line bg-raised px-2 text-sm text-ink';

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
                <div className="flex flex-wrap items-end justify-between gap-3">
                    <div>
                        <h1 className="text-3xl sm:text-4xl text-ink">Admin</h1>
                        <p className="mt-2 text-muted">Toutes les demandes d'estimation laissées sur sprea.app/estimation, les plus récentes d'abord.</p>
                    </div>
                    {leads && (
                        <div className="flex items-center gap-2 text-xs text-faint">
                            {updatedAt && <span>Mis à jour à {updatedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>}
                            <Button variant="ghost" onClick={load} disabled={loading} aria-label="Actualiser">
                                <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
                            </Button>
                            <Button variant="ghost" onClick={download} disabled={!shown.length}><Download size={15} /> CSV</Button>
                        </div>
                    )}
                </div>

                {!session ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Connectez-vous</p>
                        <Button className="mt-4" onClick={() => openLogin()}>Se connecter</Button>
                    </Card>
                ) : !me ? (
                    <Loader2 className="animate-spin text-brass" />
                ) : !me.is_admin ? (
                    <Card className="p-5 text-sm text-muted">Cette page est réservée à l'équipe SPREA.</Card>
                ) : error && !leads ? (
                    <Card className="p-4 text-sm text-coral">{error}</Card>
                ) : !leads ? (
                    <Loader2 className="animate-spin text-brass" />
                ) : (
                    <>
                        {error && <Card className="p-3 text-sm text-coral">{error}</Card>}
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                            {kpis.map(([label, n]) => (
                                <Card key={label} className="p-4">
                                    <p className="text-2xl text-ink tabular-nums">{n}</p>
                                    <p className="text-xs text-muted">{label}</p>
                                </Card>
                            ))}
                        </div>

                        <div className="flex flex-wrap gap-2">
                            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Nom, ville, code postal, email…"
                                className="h-9 flex-1 min-w-[200px] rounded-lg border border-line bg-raised px-3 text-sm text-ink outline-none focus:border-brass/70" />
                            <select value={status} onChange={e => setStatus(e.target.value as typeof status)} className={select} aria-label="Statut">
                                <option value="all">Tous les statuts</option>
                                {STATUS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                            </select>
                            <select value={routing} onChange={e => setRouting(e.target.value as typeof routing)} className={select} aria-label="Conseiller">
                                <option value="all">Avec ou sans conseiller</option>
                                <option value="assigned">Transmises à un abonné</option>
                                <option value="unassigned">Sans conseiller</option>
                            </select>
                        </div>

                        <Card className="divide-y divide-line/70">
                            {shown.length === 0 ? (
                                <p className="p-5 text-sm text-muted">{leads.length ? 'Aucune demande ne correspond aux filtres.' : 'Aucune demande pour le moment.'}</p>
                            ) : shown.map(l => {
                                const d = l.details || {};
                                const bien = [l.kind === 'maison' ? 'Maison' : 'Appartement', `${Math.round(l.surface)} m²`,
                                    d.rooms ? `${d.rooms} p.` : '', d.dpe ? `DPE ${d.dpe}` : '', d.condition ? CONDITIONS[d.condition] || '' : ''].filter(Boolean).join(' · ');
                                return (
                                    <div key={l.id} className={`p-4 sm:p-5 flex flex-col lg:flex-row gap-3 lg:items-start lg:justify-between ${fresh.has(l.id) ? 'bg-brass/10' : ''}`}>
                                        <div className="min-w-0 space-y-1">
                                            <p className="text-ink font-medium">
                                                {l.name}
                                                <span className="ml-2 rounded-full border border-brass/40 px-2 py-0.5 text-xs text-brass-light">{PROJECTS[l.project] || l.project}</span>
                                                {fresh.has(l.id) && <span className="ml-2 rounded-full bg-brass px-2 py-0.5 text-xs text-canvas">Nouvelle</span>}
                                            </p>
                                            <p className="text-sm text-muted">{when(l.created_at)} · {l.address}</p>
                                            <p className="text-sm text-ink-soft">
                                                {bien} · estimé <b className="text-ink">{euros(l.value)}</b>
                                                {l.low && l.high ? <span className="text-muted"> ({euros(l.low)} – {euros(l.high)})</span> : null}
                                            </p>
                                            <div className="flex flex-wrap gap-4 text-sm">
                                                {l.phone && <a href={`tel:${l.phone.replace(/[^0-9+]/g, '')}`} className="flex items-center gap-1.5 text-brass-light"><Phone size={14} />{l.phone}</a>}
                                                {l.email && <a href={`mailto:${l.email}`} className="flex items-center gap-1.5 text-brass-light"><Mail size={14} />{l.email}</a>}
                                                {l.lat != null && l.lon != null && (
                                                    <a href={`https://www.openstreetmap.org/?mlat=${l.lat}&mlon=${l.lon}#map=17/${l.lat}/${l.lon}`} target="_blank" rel="noreferrer"
                                                        className="flex items-center gap-1.5 text-muted hover:text-ink"><MapPin size={14} />Carte</a>
                                                )}
                                            </div>
                                            <p className="text-xs text-faint">
                                                {l.advisor ? `Transmise à ${l.advisor}` : 'Aucun abonné ne couvre cette adresse'}
                                                {l.source ? ` · source ${l.source}` : ''} · consentement le {when(l.consent_at)}
                                            </p>
                                        </div>
                                        <select value={l.status} onChange={e => update(l, e.target.value)} aria-label="Statut" className={`${select} shrink-0`}>
                                            {STATUS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                                        </select>
                                    </div>
                                );
                            })}
                        </Card>
                    </>
                )}
            </main>
            <SiteFooter />
        </div>
    );
}
