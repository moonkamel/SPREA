import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bell, Loader2, MapPin, QrCode, Trash2 } from 'lucide-react';
import { useAccount } from '../account';
import { Link, navigate } from '../router';
import { Button, Card, DpeBadge, Switch, type DPEClass } from '../ui';
import LetterDialog, { type LetterTarget } from './LetterDialog';
import { SiteFooter, SiteHeader } from './site';

interface Zone {
    id: string;
    name: string;
    radius_m: number;
    labels: string;
    kind: string | null;
    email: boolean;
    active: boolean;
    last_checked_on: string | null;
    // Zones of the other agents of the agency are shown too
    mine?: boolean;
    owner?: string | null;
}

interface Hit {
    id: string;
    zone_id: string;
    dpe_number: string;
    address: string | null;
    label: DPEClass | null;
    kind: string | null;
    surface: number | null;
    dpe_date: string | null;
    received_on: string | null;
    detail: string | null;
    created_at: string;
}

const day = (iso: string) => new Date(iso).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

export default function AlertsPage() {
    const { session, me, config, openLogin, authedFetch } = useAccount();
    const [zones, setZones] = useState<Zone[]>([]);
    const [hits, setHits] = useState<Hit[]>([]);
    const [emailEnabled, setEmailEnabled] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [zoneFilter, setZoneFilter] = useState('');
    const [letterFor, setLetterFor] = useState<LetterTarget | null>(null);

    const load = useCallback(async () => {
        if (!session) { setLoading(false); return; }
        setLoading(true);
        try {
            const res = await authedFetch('/api/alerts');
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Le chargement a échoué.');
            setZones(data.zones);
            setHits(data.hits);
            setEmailEnabled(data.email_enabled);
            setError(null);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [session, authedFetch]);

    useEffect(() => { load(); }, [load]);

    const updateZone = async (zone: Zone, fields: Partial<Zone>) => {
        const res = await authedFetch(`/api/alerts/zones/${zone.id}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields),
        });
        if (res.ok) setZones(zs => zs.map(z => (z.id === zone.id ? { ...z, ...fields } : z)));
    };

    const deleteZone = async (zone: Zone) => {
        if (!window.confirm(`Supprimer l'alerte « ${zone.name} » et ses résultats ?`)) return;
        const res = await authedFetch(`/api/alerts/zones/${zone.id}`, { method: 'DELETE' });
        if (res.ok) {
            setZones(zs => zs.filter(z => z.id !== zone.id));
            setHits(hs => hs.filter(h => h.zone_id !== zone.id));
        }
    };

    // Results grouped by the day they were found
    const groups = useMemo(() => {
        const out: { day: string; hits: Hit[] }[] = [];
        for (const h of hits.filter(h => !zoneFilter || h.zone_id === zoneFilter)) {
            const d = h.created_at.slice(0, 10);
            if (out.length && out[out.length - 1].day === d) out[out.length - 1].hits.push(h);
            else out.push({ day: d, hits: [h] });
        }
        return out;
    }, [hits, zoneFilter]);

    const zoneName = (id: string) => zones.find(z => z.id === id)?.name || '';
    const locked = error?.includes('Pro') || (me && !me.is_pro);
    const needsTerms = error?.includes('conditions');

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-5xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
                <div>
                    <h1 className="text-3xl sm:text-4xl text-ink">Alertes nouveaux DPE</h1>
                    <p className="mt-2 text-muted max-w-3xl">
                        Chaque matin, les DPE nouvellement publiés par l'ADEME dans vos secteurs. Un DPE est obligatoire avant de vendre ou de louer :
                        un nouveau DPE signale souvent un propriétaire qui prépare une mise en vente.
                    </p>
                </div>

                {!session ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Connectez-vous pour voir vos alertes</p>
                        <Button className="mt-4" onClick={() => openLogin()} disabled={!config?.auth_enabled}>Se connecter</Button>
                    </Card>
                ) : locked ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Réservé aux abonnés</p>
                        <Button className="mt-4" onClick={() => navigate('/tarifs')}>Voir les formules</Button>
                    </Card>
                ) : needsTerms ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Acceptez d'abord les conditions d'utilisation de la carte</p>
                        <Button className="mt-4" onClick={() => navigate('/prospection')}>Ouvrir la carte de prospection</Button>
                    </Card>
                ) : loading ? (
                    <Loader2 className="animate-spin text-brass" />
                ) : (
                    <>
                        {error && <Card className="p-4 text-sm text-coral">{error}</Card>}
                        <Card className="p-5 sm:p-6">
                            <h2 className="text-xl text-ink">Vos zones</h2>
                            {zones.length === 0 ? (
                                <p className="mt-3 text-sm text-muted">
                                    Aucune zone. Sur la <Link to="/prospection" className="underline text-brass-light">carte de prospection</Link>,
                                    placez-vous sur un quartier puis cliquez sur « Créer une alerte sur cette zone ».
                                </p>
                            ) : (
                                <ul className="mt-3 divide-y divide-line/70">
                                    {zones.map(z => (
                                        <li key={z.id} className="py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
                                            <div>
                                                <p className="text-ink">{z.name}{z.mine === false && z.owner && <span className="text-xs text-faint"> · zone de {z.owner}</span>}</p>
                                                <p className="text-xs text-faint">
                                                    Rayon {z.radius_m >= 1000 ? `${(z.radius_m / 1000).toFixed(1).replace('.', ',')} km` : `${z.radius_m} m`} ·
                                                    classes {z.labels.replace(/,/g, ', ')}{z.kind ? ` · ${z.kind}s` : ''}
                                                    {z.last_checked_on && ` · vérifiée le ${new Date(z.last_checked_on).toLocaleDateString('fr-FR')}`}
                                                </p>
                                            </div>
                                            {z.mine !== false && <div className="flex items-center gap-4 text-sm text-muted">
                                                <label className="flex items-center gap-2">Active <Switch checked={z.active} onChange={v => updateZone(z, { active: v })} label="Alerte active" /></label>
                                                <label className="flex items-center gap-2">Email <Switch checked={z.email} onChange={v => updateZone(z, { email: v })} label="Email du matin" /></label>
                                                <button type="button" onClick={() => deleteZone(z)} className="p-2 text-faint hover:text-coral" aria-label="Supprimer"><Trash2 size={16} /></button>
                                            </div>}
                                        </li>
                                    ))}
                                </ul>
                            )}
                            {!emailEnabled && zones.length > 0 && (
                                <p className="mt-3 text-xs text-faint">L'envoi d'emails n'est pas encore activé sur SPREA : les nouveaux DPE apparaissent ici chaque matin.</p>
                            )}
                        </Card>

                        <Card className="p-5 sm:p-6">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <h2 className="text-xl text-ink flex items-center gap-2"><Bell size={18} className="text-brass" />Nouveaux DPE</h2>
                                {zones.length > 1 && (
                                    <select value={zoneFilter} onChange={e => setZoneFilter(e.target.value)} aria-label="Zone"
                                        className="h-9 rounded-lg border border-line bg-raised px-2 text-sm text-ink">
                                        <option value="">Toutes les zones</option>
                                        {zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
                                    </select>
                                )}
                            </div>
                            {groups.length === 0 ? (
                                <p className="mt-3 text-sm text-muted">Aucun nouveau DPE pour l'instant. Les zones sont vérifiées chaque matin.</p>
                            ) : groups.map(g => (
                                <div key={g.day} className="mt-5">
                                    <p className="text-sm text-brass capitalize">{day(g.day)} · {g.hits.length} DPE</p>
                                    <ul className="mt-2 divide-y divide-line/70">
                                        {g.hits.map(h => (
                                            <li key={h.id} className="py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
                                                <div className="flex items-start gap-3 min-w-0">
                                                    <DpeBadge label={h.label} size="sm" />
                                                    <div className="min-w-0">
                                                        <p className="text-sm text-ink truncate">{h.address}</p>
                                                        <p className="text-xs text-faint">
                                                            {[h.kind, h.surface ? `${Math.round(h.surface)} m²` : null, h.detail,
                                                              h.dpe_date ? `DPE du ${new Date(h.dpe_date).toLocaleDateString('fr-FR')}` : null, zoneName(h.zone_id)]
                                                                .filter(Boolean).join(' · ')}
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="flex gap-4 text-xs shrink-0 ml-10 sm:ml-0">
                                                    <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1"
                                                        onClick={() => navigate(`/?dpe=${encodeURIComponent(h.dpe_number)}`)}>
                                                        <MapPin size={12} />Simuler
                                                    </button>
                                                    {h.address && h.label && (
                                                        <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                            onClick={() => setLetterFor({ address: h.address!, label: h.label!, dpeNumber: h.dpe_number })}>
                                                            <QrCode size={12} />Courrier avec QR code
                                                        </button>
                                                    )}
                                                </div>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                            <p className="mt-5 text-xs text-faint">
                                Source : DPE des logements existants, ADEME (Licence Ouverte), publiés avec quelques jours de délai. Usage soumis à l'article 14 des CGV.
                                Résultats conservés 6 mois.
                            </p>
                        </Card>
                    </>
                )}
            </main>
            <SiteFooter />
            {letterFor && <LetterDialog target={letterFor} onClose={() => setLetterFor(null)} />}
        </div>
    );
}
