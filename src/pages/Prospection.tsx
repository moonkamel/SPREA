import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Bell, Download, Loader2, Lock, MapPin, QrCode, Search, ShieldCheck } from 'lucide-react';
import { useAccount } from '../account';
import { Link, navigate } from '../router';
import { Button, Card, DPE_COLORS, DpeBadge, type DPEClass } from '../ui';
import LetterDialog, { type LetterTarget } from './LetterDialog';
import { SiteFooter, SiteHeader } from './site';

interface Dpe {
    number: string;
    label: DPEClass;
    kind: string | null;
    surface: number | null;
    date: string | null;
    period: string | null;
    detail: string | number | null;
}

interface Address {
    address?: string;
    lat: number;
    lon: number;
    worst: DPEClass;
    dpe?: Dpe[];
    count?: number;
}

interface Result {
    locked: boolean;
    // Pro, but the current terms of the map (CGV article 14) are not accepted yet
    terms_required?: boolean;
    terms_version?: string;
    addresses: Address[];
    dwellings: number;
    total: number;
    truncated: boolean;
}

const MIN_ZOOM = 15;
const LABEL_OPTIONS: DPEClass[] = ['G', 'F', 'E'];
const KINDS = [
    { value: '', label: 'Tous les biens' },
    { value: 'maison', label: 'Maisons' },
    { value: 'appartement', label: 'Appartements' },
    { value: 'immeuble', label: 'Immeubles entiers' },
];
const SINCE = [
    { value: '', label: 'Tous les DPE' },
    { value: '2024', label: 'DPE depuis 2024' },
    { value: '2025', label: 'DPE depuis 2025' },
];

// IGN Plan v2 (Géoplateforme), free and up to date for France
const TILES = 'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2'
    + '&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}';

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('fr-FR') : '');

function toCsv(addresses: Address[]) {
    const rows = [['adresse', 'classe', 'type', 'surface_m2', 'complement', 'date_dpe', 'periode_construction', 'numero_dpe']];
    for (const a of addresses) {
        for (const d of a.dpe || []) {
            rows.push([a.address || '', d.label, d.kind || '', d.surface != null ? String(d.surface) : '', d.detail != null ? String(d.detail) : '',
                d.date || '', d.period || '', d.number]);
        }
    }
    return rows.map(r => r.map(v => `"${v.replace(/"/g, '""')}"`).join(';')).join('\n');
}

export default function ProspectionPage() {
    const { session, me, config, openLogin, authedFetch } = useAccount();
    const mapRef = useRef<L.Map | null>(null);
    const layerRef = useRef<L.LayerGroup | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const markers = useRef<Map<string, L.CircleMarker>>(new Map());
    const [labels, setLabels] = useState<DPEClass[]>(['G', 'F']);
    const [kind, setKind] = useState('');
    const [since, setSince] = useState('');
    const [zoom, setZoom] = useState(13);
    const [result, setResult] = useState<Result | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [query, setQuery] = useState('');
    const [reload, setReload] = useState(0);
    const [accepting, setAccepting] = useState(false);
    const [letterFor, setLetterFor] = useState<LetterTarget | null>(null);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
    const [boundsKey, setBoundsKey] = useState('');

    // Map
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return;
        const map = L.map(containerRef.current, { zoomControl: true }).setView([50.6329, 3.0573], 13);
        L.tileLayer(TILES, { maxZoom: 19, minZoom: 6, attribution: '© IGN, données DPE ADEME' }).addTo(map);
        layerRef.current = L.layerGroup().addTo(map);
        const update = () => {
            setZoom(map.getZoom());
            const b = map.getBounds();
            setBoundsKey([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(v => v.toFixed(4)).join(','));
        };
        map.on('moveend', update);
        // Actions in the popups (plain HTML, built by Leaflet)
        map.on('popupopen', e => {
            e.popup.getElement()?.querySelectorAll<HTMLElement>('[data-action]').forEach(el => {
                el.onclick = ev => {
                    ev.preventDefault();
                    const dpe = el.dataset.dpe || '';
                    if (el.dataset.action === 'simulate') navigate(`/?dpe=${encodeURIComponent(dpe)}`);
                    else setLetterFor({ address: el.dataset.address || '', label: el.dataset.label as DPEClass, dpeNumber: dpe });
                };
            });
        });
        update();
        mapRef.current = map;
        return () => { map.remove(); mapRef.current = null; };
    }, []);

    // Data for the visible area
    useEffect(() => {
        if (!session || zoom < MIN_ZOOM || !boundsKey || !labels.length) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            setLoading(true);
            setError(null);
            try {
                const params = new URLSearchParams({ bbox: boundsKey, labels: labels.join(',') });
                if (kind) params.set('kind', kind);
                if (since) params.set('since', since);
                const res = await authedFetch(`/api/prospection?${params}`, { signal: controller.signal });
                if (!res.ok) {
                    const detail = await res.json().catch(() => ({}));
                    throw new Error(res.status === 429 ? 'Trop de recherches : patientez une minute.' : detail.detail || 'La recherche a échoué.');
                }
                setResult(await res.json());
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }, 450);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [session, zoom, boundsKey, labels, kind, since, authedFetch, reload]);

    const showDetails = !!result && !result.locked && !result.terms_required;

    // Markers
    useEffect(() => {
        const layer = layerRef.current;
        if (!layer) return;
        layer.clearLayers();
        markers.current.clear();
        if (!result || zoom < MIN_ZOOM) return;
        for (const a of result.addresses) {
            const n = a.dpe?.length ?? a.count ?? 1;
            const marker = L.circleMarker([a.lat, a.lon], {
                radius: Math.min(14, 5 + Math.sqrt(n) * 2),
                color: '#0A0F1A', weight: 1, fillColor: DPE_COLORS[a.worst].bg, fillOpacity: 0.9,
            });
            if (showDetails && a.dpe) {
                const link = 'color:#8A6417;font-weight:600;text-decoration:none;cursor:pointer';
                const lines = a.dpe.slice(0, 8).map(d =>
                    `<li style="margin:3px 0"><b style="color:${DPE_COLORS[d.label].bg}">${d.label}</b> · ${escapeHtml(d.kind || 'Logement')}`
                    + `${d.surface ? ` · ${Math.round(d.surface)} m²` : ''}${d.detail ? ` · ${escapeHtml(String(d.detail))}` : ''}`
                    + ` <span style="color:#666">(${formatDate(d.date)})</span>`
                    + (d.number ? ` · <a href="#" data-action="simulate" data-dpe="${escapeHtml(d.number)}" style="${link}">Simuler</a>` : '')
                    + '</li>').join('');
                const first = a.dpe[0];
                marker.bindPopup(`<b>${escapeHtml(a.address || '')}</b><ul style="margin:6px 0 0;padding-left:16px">${lines}</ul>`
                    + (a.dpe.length > 8 ? `<div style="color:#666">+ ${a.dpe.length - 8} autres</div>` : '')
                    + (first?.number ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #ddd"><a href="#" data-action="letter"`
                        + ` data-dpe="${escapeHtml(first.number)}" data-address="${escapeHtml(a.address || '')}" data-label="${a.worst}" style="${link}">`
                        + 'Courrier avec QR code</a></div>' : ''), { minWidth: 260 });
                markers.current.set(a.address || `${a.lat},${a.lon}`, marker);
            } else {
                marker.bindTooltip(`${n} logement${n > 1 ? 's' : ''} classé${n > 1 ? 's' : ''} ${a.worst}`);
            }
            marker.addTo(layer);
        }
    }, [result, showDetails, zoom]);

    const locate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim() || !mapRef.current) return;
        try {
            const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(query)}&limit=1`);
            const data = await res.json();
            const f = data.features?.[0];
            if (!f) { setError('Adresse ou commune introuvable.'); return; }
            const [lon, lat] = f.geometry.coordinates;
            mapRef.current.setView([lat, lon], f.properties.type === 'municipality' ? 15 : 17);
        } catch {
            setError('La recherche d\'adresse a échoué.');
        }
    };

    const toggleLabel = (l: DPEClass) => setLabels(prev => prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l]);

    const focus = (a: Address) => {
        mapRef.current?.setView([a.lat, a.lon], Math.max(mapRef.current.getZoom(), 17));
        setTimeout(() => markers.current.get(a.address || `${a.lat},${a.lon}`)?.openPopup(), 300);
    };


    // Daily alert on the visible area (center, radius up to 3 km)
    const createAlert = async () => {
        const map = mapRef.current;
        if (!map) return;
        const name = window.prompt('Nom de la zone d\'alerte (ex. : Vieux-Lille)');
        if (!name?.trim()) return;
        const center = map.getCenter();
        const radius = Math.round(Math.min(3000, Math.max(200, center.distanceTo(map.getBounds().getNorthEast()))));
        setAlertMessage(null);
        try {
            const res = await authedFetch('/api/alerts/zones', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim().slice(0, 60), lat: center.lat, lon: center.lng, radius_m: radius,
                    labels: labels.length ? labels : ['E', 'F', 'G'], kind: kind || null }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || "L'alerte n'a pas pu être créée.");
            setAlertMessage(`Alerte « ${name.trim()} » créée : ${data.new_hits} DPE reçus ces 14 derniers jours. Les nouveaux arriveront chaque matin.`);
        } catch (e) {
            setAlertMessage((e as Error).message);
        }
    };

    const exportCsv = () => {
        if (!result) return;
        const blob = new Blob(['﻿' + toCsv(result.addresses)], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'prospection-dpe.csv';
        link.click();
        URL.revokeObjectURL(url);
    };

    // The acceptance is recorded on the server (proof of the accepted version)
    const accept = async () => {
        if (!result?.terms_version) return;
        setAccepting(true);
        setError(null);
        try {
            const res = await authedFetch('/api/prospection/terms', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ terms_version: result.terms_version, accept: true }),
            });
            if (!res.ok) {
                const detail = await res.json().catch(() => ({}));
                throw new Error(detail.detail || "L'acceptation n'a pas pu être enregistrée.");
            }
            setReload(r => r + 1);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setAccepting(false);
        }
    };

    const visible = useMemo(() => (showDetails ? result!.addresses : []), [result, showDetails]);
    const open = useCallback((d: Dpe) => navigate(`/?dpe=${encodeURIComponent(d.number)}`), []);

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
                <div className="mb-6">
                    <h1 className="text-3xl sm:text-4xl text-ink">Carte de prospection</h1>
                    <p className="mt-2 text-muted max-w-3xl">
                        Les logements classés G, F ou E de votre secteur, d'après les DPE publiés par l'ADEME. Repérez les propriétaires
                        concernés par la loi Climat, proposez-leur une estimation et un plan de rénovation chiffré.
                    </p>
                </div>

                <div className="flex flex-col lg:flex-row gap-3 lg:items-center mb-4">
                    <form onSubmit={locate} className="flex flex-1 items-center rounded-xl border border-line bg-raised focus-within:border-brass/70">
                        <Search size={16} className="ml-3.5 text-faint" />
                        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Commune, quartier ou adresse"
                            className="w-full bg-transparent px-3 h-11 text-ink outline-none" aria-label="Commune ou adresse" />
                    </form>
                    <div className="flex gap-2" role="group" aria-label="Classes DPE">
                        {LABEL_OPTIONS.map(l => (
                            <button key={l} type="button" onClick={() => toggleLabel(l)} aria-pressed={labels.includes(l)}
                                className={`h-11 w-11 rounded-xl font-bold border-2 transition-opacity ${labels.includes(l) ? 'opacity-100' : 'opacity-30'}`}
                                style={{ backgroundColor: DPE_COLORS[l].bg, color: DPE_COLORS[l].fg, borderColor: labels.includes(l) ? '#E3C98F' : 'transparent' }}>
                                {l}
                            </button>
                        ))}
                    </div>
                    <select value={kind} onChange={e => setKind(e.target.value)} aria-label="Type de bien"
                        className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                        {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                    <select value={since} onChange={e => setSince(e.target.value)} aria-label="Date du DPE"
                        className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                        {SINCE.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                    </select>
                </div>

                <div className="grid lg:grid-cols-[1fr_380px] gap-4">
                    <div className="relative rounded-2xl overflow-hidden border border-line">
                        <div ref={containerRef} className="h-[60vh] lg:h-[70vh] w-full bg-raised" />
                        <div className="absolute top-3 left-14 right-3 z-[500] flex flex-wrap gap-2 pointer-events-none">
                            {zoom < MIN_ZOOM && (
                                <span className="rounded-lg bg-canvas/90 px-3 py-1.5 text-sm text-ink">Zoomez sur un quartier pour afficher les logements.</span>
                            )}
                            {zoom >= MIN_ZOOM && result && (
                                <span className="rounded-lg bg-canvas/90 px-3 py-1.5 text-sm text-ink tabular-nums">
                                    {result.dwellings.toLocaleString('fr-FR')} logement{result.dwellings > 1 ? 's' : ''} · {result.addresses.length.toLocaleString('fr-FR')} adresse{result.addresses.length > 1 ? 's' : ''}
                                    {result.truncated && ' (zone dense : zoomez pour tout voir)'}
                                </span>
                            )}
                            {loading && <span className="rounded-lg bg-canvas/90 px-3 py-1.5 text-sm text-ink flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Chargement</span>}
                        </div>
                    </div>

                    <div className="space-y-4">
                        {error && <Card className="p-4 text-sm text-coral">{error}</Card>}

                        {!session ? (
                            <Card className="p-5">
                                <p className="text-ink font-medium">Connectez-vous pour explorer la carte</p>
                                <p className="mt-1 text-sm text-muted">La carte affiche le nombre de passoires par secteur ; les adresses sont réservées aux abonnés.</p>
                                <Button className="mt-4 w-full" onClick={() => openLogin('Connectez-vous pour utiliser la carte de prospection.')}
                                    disabled={!config?.auth_enabled}>Se connecter</Button>
                            </Card>
                        ) : result?.locked ? (
                            <Card className="p-5">
                                <p className="text-ink font-medium flex items-center gap-2"><Lock size={16} className="text-brass" />Adresses réservées aux abonnés</p>
                                <p className="mt-2 text-sm text-muted">
                                    {result.dwellings.toLocaleString('fr-FR')} logements classés {labels.join(', ')} dans cette zone.
                                    Avec l'abonnement : les adresses, le détail de chaque DPE, l'export CSV et un modèle de courrier par adresse.
                                </p>
                                <Button className="mt-4 w-full" onClick={() => navigate('/tarifs')}>Voir les formules</Button>
                            </Card>
                        ) : result?.terms_required ? (
                            <Card className="p-5 text-sm">
                                <p className="text-ink font-medium flex items-center gap-2"><ShieldCheck size={16} className="text-brass" />Avant d'utiliser ces adresses</p>
                                <ul className="mt-3 space-y-2 text-muted list-disc pl-5">
                                    <li>Ce sont des données publiques de l'ADEME (Licence Ouverte) : elles indiquent une adresse et un DPE, jamais le nom du propriétaire. Ne les croisez pas avec d'autres fichiers pour identifier les personnes.</li>
                                    <li>Un courrier adressé au logement est une prospection : indiquez l'origine des données (DPE publics de l'ADEME) et un moyen simple de ne plus être contacté, puis respectez ces demandes.</li>
                                    <li>Ne conservez les adresses que le temps de votre campagne. Pas de démarchage téléphonique à partir de ces données.</li>
                                    <li>Ces règles résument les principes du RGPD ; faites valider votre campagne par votre conseil ou consultez cnil.fr.</li>
                                </ul>
                                <p className="mt-3 text-muted">
                                    En affichant les adresses, vous acceptez les conditions d'utilisation de la carte prévues à l'
                                    <Link to="/cgv" className="underline text-brass hover:text-brass-light">article 14 des CGV</Link>.
                                </p>
                                <Button className="mt-4 w-full" onClick={accept} disabled={accepting}>
                                    {accepting && <Loader2 size={14} className="animate-spin" />}J'accepte, afficher les adresses
                                </Button>
                            </Card>
                        ) : null}

                        {showDetails && (
                            <Card className="p-4">
                                <Button variant="secondary" className="h-10 w-full" onClick={createAlert}>
                                    <Bell size={14} />Créer une alerte sur cette zone
                                </Button>
                                <p className="mt-2 text-xs text-faint">
                                    {alertMessage || 'Chaque matin, les nouveaux DPE de la zone visible, avec les filtres choisis. Un nouveau DPE annonce souvent une vente ou une location.'}
                                    {alertMessage && <> <Link to="/alertes" className="underline text-brass-light">Voir les alertes</Link></>}
                                </p>
                            </Card>
                        )}

                        {showDetails && (
                            <Card className="p-0 overflow-hidden">
                                <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-line">
                                    <p className="text-sm text-ink font-medium">{visible.length.toLocaleString('fr-FR')} adresses</p>
                                    <Button variant="secondary" className="h-9 px-3" onClick={exportCsv} disabled={!visible.length}>
                                        <Download size={14} />CSV
                                    </Button>
                                </div>
                                <ul className="max-h-[60vh] overflow-y-auto divide-y divide-line/70">
                                    {visible.slice(0, 300).map(a => (
                                        <li key={a.address} className="px-4 py-3">
                                            <button type="button" onClick={() => focus(a)} className="flex items-start gap-3 text-left w-full">
                                                <DpeBadge label={a.worst} size="sm" />
                                                <span className="min-w-0">
                                                    <span className="block text-sm text-ink truncate">{a.address}</span>
                                                    <span className="block text-xs text-faint">
                                                        {a.dpe!.length} logement{a.dpe!.length > 1 ? 's' : ''} · {a.dpe![0].kind || 'Logement'}
                                                        {a.dpe![0].surface ? ` · ${Math.round(a.dpe![0].surface)} m²` : ''} · DPE du {formatDate(a.dpe![0].date)}
                                                    </span>
                                                </span>
                                            </button>
                                            <div className="mt-2 ml-10 flex flex-wrap gap-3 text-xs">
                                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1" onClick={() => open(a.dpe![0])}>
                                                    <MapPin size={12} />Simuler la rénovation
                                                </button>
                                                <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                    onClick={() => setLetterFor({ address: a.address || '', label: a.worst, dpeNumber: a.dpe![0].number })}>
                                                    <QrCode size={12} />Courrier avec QR code
                                                </button>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                                {visible.length > 300 && <p className="px-4 py-2 text-xs text-faint border-t border-line">300 premières adresses affichées : l'export CSV contient tout.</p>}
                            </Card>
                        )}

                        {me && !me.is_pro && !result && session && zoom >= MIN_ZOOM && !loading && (
                            <Card className="p-4 text-sm text-muted">Déplacez la carte pour lancer la recherche.</Card>
                        )}
                    </div>
                </div>

                <p className="mt-6 text-xs text-faint max-w-4xl">
                    Source : DPE des logements existants, ADEME (Licence Ouverte 2.0), géolocalisés par la Base Adresse Nationale. Le DPE affiché est le plus
                    récent parmi les DPE E, F ou G du logement : un DPE plus favorable établi depuis, après travaux, n'est pas vérifié. Fond de carte © IGN.
                </p>
            </main>
            <SiteFooter />
            {letterFor && <LetterDialog target={letterFor} onClose={() => setLetterFor(null)} />}
        </div>
    );
}
