import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Bell, Building2, Download, Loader2, LocateFixed, Lock, MapPin, QrCode, Search } from 'lucide-react';
import { useAccount } from '../account';
import { Link, navigate } from '../router';
import { useSeo } from '../seo';
import { Button, Card, DPE_COLORS, DpeBadge, type DPEClass } from '../ui';
import LetterDialog, { type LetterTarget } from './LetterDialog';
import { MonoproList, MonoproSheet, NO_DPE_COLOR, monoColor, type MonoBuilding, type SheetTarget } from './Monopro';
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
    addresses: Address[];
    dwellings: number;
    total: number;
    truncated: boolean;
}

// Below this zoom the loaded area would only be a dot on the map
const MIN_ZOOM = 12;
// Loaded area, in degrees: the server accepts 0.045 (about 3 km x 5 km)
const MAX_SPAN = 0.044;
// The map opens on the visitor's area: 1.5 km around their approximate position
const START_RADIUS = 1500;
const DEFAULT_CENTER: [number, number] = [50.6329, 3.0573];
const VIEW_KEY = 'sprea-prospection-view';
const BRASS = '#C9A45C';

interface Area { key: string; clamped: boolean; bounds: L.LatLngBounds }

// The visible map, reduced around its center when larger than the server limit
function searchArea(map: L.Map): Area {
    const b = map.getBounds();
    const c = map.getCenter();
    let [w, s, e, n] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    let clamped = false;
    if (e - w > MAX_SPAN) { w = c.lng - MAX_SPAN / 2; e = c.lng + MAX_SPAN / 2; clamped = true; }
    if (n - s > MAX_SPAN) { s = c.lat - MAX_SPAN / 2; n = c.lat + MAX_SPAN / 2; clamped = true; }
    return { key: [w, s, e, n].map(v => v.toFixed(4)).join(','), clamped, bounds: L.latLngBounds([s, w], [n, e]) };
}

function savedView(): { lat: number; lon: number; zoom: number } | null {
    try { return JSON.parse(sessionStorage.getItem(VIEW_KEY) || 'null'); } catch { return null; }
}
const LABEL_OPTIONS: DPEClass[] = ['G', 'F', 'E'];
const KINDS = [
    { value: '', label: 'Tous les biens' },
    { value: 'maison', label: 'Maisons' },
    { value: 'appartement', label: 'Appartements' },
];
// Recent DPE only: a new DPE usually announces a sale or a letting.
// DPE reach the ADEME within a few days: the last week may still fill up.
const SINCE = [
    { value: '7', label: 'DPE des 7 derniers jours' },
    { value: '31', label: 'DPE du dernier mois' },
    { value: '92', label: 'DPE des 3 derniers mois' },
    { value: '183', label: 'DPE des 6 derniers mois' },
    { value: '365', label: 'DPE des 12 derniers mois' },
];
const DEFAULT_SINCE = '183';
const daysAgo = (days: string) => new Date(Date.now() - Number(days) * 86400000).toISOString().slice(0, 10);

// IGN Plan v2 (Géoplateforme), free and up to date for France
const TILES = 'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2'
    + '&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}';

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
// Date of the most recent DPE at an address
const latestDate = (a: Address) => (a.dpe || []).reduce((m, d) => (d.date && d.date > m ? d.date : m), '');
// DPE of a whole building: it leads to the building sheet, not to the simulator of a dwelling
const isBuilding = (d: Dpe) => (d.kind || '').toLowerCase() === 'immeuble';
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
    useSeo({ title: 'Carte de prospection · SPREA', noindex: true });
    const mapRef = useRef<L.Map | null>(null);
    const layerRef = useRef<L.LayerGroup | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const markers = useRef<Map<string, L.CircleMarker>>(new Map());
    const homeRef = useRef<L.Circle | null>(null);
    const areaRef = useRef<L.Rectangle | null>(null);
    const [labels, setLabels] = useState<DPEClass[]>(['G', 'F']);
    const [kind, setKind] = useState('');
    const [since, setSince] = useState(DEFAULT_SINCE);
    const [zoom, setZoom] = useState(13);
    const [result, setResult] = useState<Result | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [query, setQuery] = useState('');
    const [letterFor, setLetterFor] = useState<LetterTarget | null>(null);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
    const [area, setArea] = useState<Area | null>(null);
    // The first search waits for the starting position
    const [ready, setReady] = useState(false);
    const [locating, setLocating] = useState(false);
    const [framed, setFramed] = useState(false);
    // 'immeubles': whole buildings held by a single owner (BDNB)
    const [mode, setMode] = useState<'dpe' | 'immeubles'>('dpe');
    const [minLog, setMinLog] = useState('3');
    const [monoDpe, setMonoDpe] = useState<'all' | 'fg'>('all');
    const [mono, setMono] = useState<{ buildings: MonoBuilding[]; truncated: boolean } | null>(null);
    const [sheet, setSheet] = useState<SheetTarget | null>(null);

    // Centers the map on a place, with the starting circle around it
    const goHome = useCallback((lat: number, lon: number) => {
        const map = mapRef.current;
        if (!map) return;
        homeRef.current?.remove();
        homeRef.current = L.circle([lat, lon], {
            radius: START_RADIUS, color: BRASS, weight: 2, opacity: 0.9, dashArray: '6 6', fillColor: BRASS, fillOpacity: 0.05, interactive: false,
        }).addTo(map);
        // Zoomed on the circle itself
        map.fitBounds(L.latLng(lat, lon).toBounds(START_RADIUS * 2), { animate: false, padding: [12, 12] });
    }, []);

    // Map
    useEffect(() => {
        if (!containerRef.current || mapRef.current) return;
        const saved = savedView();
        let started = !!saved;
        const map = L.map(containerRef.current, { zoomControl: false, preferCanvas: true, zoomSnap: 0.25 })
            .setView(saved ? [saved.lat, saved.lon] : DEFAULT_CENTER, saved?.zoom ?? 14);
        L.control.zoom({ position: 'topright' }).addTo(map);
        L.tileLayer(TILES, { maxZoom: 19, minZoom: 6, attribution: '© IGN, données DPE ADEME', className: 'sprea-tiles' }).addTo(map);
        layerRef.current = L.layerGroup().addTo(map);
        const update = () => {
            setZoom(map.getZoom());
            setArea(searchArea(map));
            // Remembered once placed on the visitor's area (back from a simulation)
            if (!started) return;
            const c = map.getCenter();
            try { sessionStorage.setItem(VIEW_KEY, JSON.stringify({ lat: c.lat, lon: c.lng, zoom: map.getZoom() })); } catch { /* private mode */ }
        };
        map.on('moveend', update);
        // Actions in the popups (plain HTML, built by Leaflet)
        map.on('popupopen', e => {
            e.popup.getElement()?.querySelectorAll<HTMLElement>('[data-action]').forEach(el => {
                el.onclick = ev => {
                    ev.preventDefault();
                    const dpe = el.dataset.dpe || '';
                    if (el.dataset.action === 'simulate') navigate(`/?dpe=${encodeURIComponent(dpe)}`);
                    else if (el.dataset.action === 'building') setSheet({ near: { lat: Number(el.dataset.lat), lon: Number(el.dataset.lon), address: el.dataset.address || '' } });
                    else setLetterFor({ address: el.dataset.address || '', label: el.dataset.label as DPEClass, dpeNumber: dpe });
                };
            });
        });
        mapRef.current = map;
        update();
        // From the simulator of a building DPE: that building and its sheet
        const params = new URLSearchParams(window.location.search);
        const [plat, plon] = (params.get('immeuble') || '').split(',').map(Number);
        if (Number.isFinite(plat) && Number.isFinite(plon) && params.get('immeuble')) {
            // Next tick, once mounted for good (React may mount the map twice in development)
            Promise.resolve().then(() => {
                if (mapRef.current !== map) return;
                started = true;
                goHome(plat, plon);
                setReady(true);
                setMode('immeubles');
                setSheet({ near: { lat: plat, lon: plon, address: params.get('adresse') || '' } });
            });
        } else if (saved) {
            // Back from a simulation: same place as before
            setReady(true);
        } else {
            // First visit in this tab: the visitor's area, from their IP address
            // (city level, no permission asked), else the default place
            fetch('/api/geo')
                .then(res => (res.ok ? res.json() : null))
                .catch(() => null)
                .then(geo => {
                    if (mapRef.current !== map) return;
                    started = true;
                    if (geo?.lat != null && geo?.lon != null) goHome(geo.lat, geo.lon);
                    else goHome(...DEFAULT_CENTER);
                    setReady(true);
                });
        }
        return () => { map.remove(); mapRef.current = null; };
    }, [goHome]);

    // Precise position, only on request (the browser asks for permission)
    const aroundMe = () => {
        if (!navigator.geolocation) { setError('La localisation n\'est pas disponible sur cet appareil : tapez une adresse.'); return; }
        setLocating(true);
        navigator.geolocation.getCurrentPosition(
            pos => { setLocating(false); setError(null); goHome(pos.coords.latitude, pos.coords.longitude); },
            () => { setLocating(false); setError('Position indisponible : autorisez la localisation ou tapez une adresse.'); },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
        );
    };

    // Outline of the loaded area when the map shows more than that
    useEffect(() => {
        const map = mapRef.current;
        areaRef.current?.remove();
        areaRef.current = null;
        const home = homeRef.current;
        // Not needed while the starting circle fits in the loaded area
        const show = !!map && !!area?.clamped && zoom >= MIN_ZOOM && !!session
            && !(home && map.hasLayer(home) && area.bounds.contains(home.getBounds()));
        setFramed(show);
        if (!show) return;
        areaRef.current = L.rectangle(area.bounds, { color: BRASS, weight: 1, opacity: 0.45, dashArray: '2 6', fill: false, interactive: false }).addTo(map);
    }, [area, zoom, session]);

    // Data for the visible area
    const areaKey = area?.key;
    const zoomOk = zoom >= MIN_ZOOM;
    // Last loaded area: zooming in or moving inside it needs no new search
    const loaded = useRef<{ box: number[]; filters: string } | null>(null);
    useEffect(() => {
        if (mode !== 'dpe' || !session || !ready || !zoomOk || !areaKey || !labels.length) return;
        const box = areaKey.split(',').map(Number);
        const filters = [labels.join(','), kind, since, me?.is_pro].join('|');
        const last = loaded.current;
        if (last && last.filters === filters && box[0] >= last.box[0] && box[1] >= last.box[1] && box[2] <= last.box[2] && box[3] <= last.box[3]) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            setLoading(true);
            setError(null);
            try {
                const params = new URLSearchParams({ bbox: areaKey, labels: labels.join(',') });
                if (kind) params.set('kind', kind);
                params.set('since', daysAgo(since));
                const res = await authedFetch(`/api/prospection?${params}`, { signal: controller.signal });
                if (!res.ok) {
                    const detail = await res.json().catch(() => ({}));
                    throw new Error(res.status === 429 ? 'Trop de recherches : patientez une minute.' : detail.detail || 'La recherche a échoué.');
                }
                const data: Result = await res.json();
                // A truncated result is only the start of a dense area: search again on any move
                loaded.current = data.truncated ? null : { box, filters };
                setResult(data);
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }, 450);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [mode, session, ready, zoomOk, areaKey, labels, kind, since, authedFetch, me?.is_pro]);

    // Whole buildings for the visible area
    const monoLoaded = useRef<{ box: number[]; filters: string } | null>(null);
    useEffect(() => {
        if (mode !== 'immeubles' || !session || !ready || !zoomOk || !areaKey) return;
        const box = areaKey.split(',').map(Number);
        const filters = [minLog, monoDpe].join('|');
        const last = monoLoaded.current;
        if (last && last.filters === filters && box[0] >= last.box[0] && box[1] >= last.box[1] && box[2] <= last.box[2] && box[3] <= last.box[3]) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            setLoading(true);
            setError(null);
            try {
                const params = new URLSearchParams({ bbox: areaKey, owner: 'company', min_log: minLog, dpe: monoDpe });
                const res = await authedFetch(`/api/monopro?${params}`, { signal: controller.signal });
                if (!res.ok) {
                    const detail = await res.json().catch(() => ({}));
                    throw new Error(res.status === 429 ? 'Trop de recherches : patientez une minute.' : detail.detail || 'La recherche a échoué.');
                }
                const data = await res.json();
                monoLoaded.current = data.truncated ? null : { box, filters };
                setMono(data);
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setError((e as Error).message);
            } finally {
                setLoading(false);
            }
        }, 450);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [mode, session, ready, zoomOk, areaKey, minLog, monoDpe, authedFetch]);

    const showDetails = !!result && !result.locked;

    // Markers
    useEffect(() => {
        const layer = layerRef.current;
        if (!layer) return;
        layer.clearLayers();
        markers.current.clear();
        if (mode === 'immeubles') {
            if (!mono || !zoomOk) return;
            for (const b of mono.buildings) {
                const marker = L.circleMarker([b.lat, b.lon], {
                    radius: Math.min(16, 4 + Math.sqrt(b.nb_log) * 2),
                    // Gold outline: owned by a company (owner identified)
                    color: b.owner ? '#E3C98F' : '#0A0F1A', weight: b.owner ? 2 : 1.5, opacity: 0.95,
                    fillColor: monoColor(b), fillOpacity: 0.95,
                });
                marker.bindTooltip(`${escapeHtml(b.address || '')}<br>${b.nb_log} logements · ${escapeHtml(b.owner ? `${b.owner.legal_form || ''} ${b.owner.name || ''}` : 'propriétaire non identifié')}`);
                marker.on('click', () => setSheet({ id: b.id }));
                marker.addTo(layer);
            }
            return;
        }
        if (!result || !zoomOk) return;
        for (const a of result.addresses) {
            const n = a.dpe?.length ?? a.count ?? 1;
            const marker = L.circleMarker([a.lat, a.lon], {
                radius: Math.min(14, 4.5 + Math.sqrt(n) * 2),
                color: '#0A0F1A', weight: 1.5, opacity: 0.9, fillColor: DPE_COLORS[a.worst].bg, fillOpacity: 0.95,
            });
            marker.on('mouseover', () => marker.setStyle({ color: '#E3C98F', weight: 2.5 }));
            marker.on('mouseout', () => marker.setStyle({ color: '#0A0F1A', weight: 1.5 }));
            if (showDetails && a.dpe) {
                const link = 'color:#E3C98F;font-weight:600;text-decoration:none;cursor:pointer';
                const lines = a.dpe.slice(0, 8).map(d =>
                    `<li style="margin:3px 0"><b style="color:${DPE_COLORS[d.label].bg}">${d.label}</b> · ${escapeHtml(d.kind || 'Logement')}`
                    + `${d.surface ? ` · ${Math.round(d.surface)} m²` : ''}${d.detail ? ` · ${escapeHtml(String(d.detail))}` : ''}`
                    + ` <span style="color:#97A1B3">(${formatDate(d.date)})</span>`
                    + (isBuilding(d) ? ` · <a href="#" data-action="building" data-lat="${a.lat}" data-lon="${a.lon}" data-address="${escapeHtml(a.address || '')}" style="${link}">Fiche immeuble</a>`
                        : d.number ? ` · <a href="#" data-action="simulate" data-dpe="${escapeHtml(d.number)}" style="${link}">Simuler</a>` : '')
                    + '</li>').join('');
                const first = a.dpe[0];
                marker.bindPopup(`<b>${escapeHtml(a.address || '')}</b><ul style="margin:6px 0 0;padding-left:16px">${lines}</ul>`
                    + (a.dpe.length > 8 ? `<div style="color:#97A1B3">+ ${a.dpe.length - 8} autres</div>` : '')
                    + (first?.number ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #25324C"><a href="#" data-action="letter"`
                        + ` data-dpe="${escapeHtml(first.number)}" data-address="${escapeHtml(a.address || '')}" data-label="${a.worst}" style="${link}">`
                        + 'Courrier avec QR code</a></div>' : ''), { minWidth: 260 });
                markers.current.set(a.address || `${a.lat},${a.lon}`, marker);
            } else {
                marker.bindTooltip(`${n} logement${n > 1 ? 's' : ''} classé${n > 1 ? 's' : ''} ${a.worst}`);
            }
            marker.addTo(layer);
        }
    }, [mode, mono, result, showDetails, zoomOk]);

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

    // Newest DPE first: the hottest prospects at the top of the list
    const visible = useMemo(() => {
        if (!showDetails) return [];
        return [...result!.addresses].sort((a, b) => latestDate(b).localeCompare(latestDate(a)));
    }, [result, showDetails]);
    const open = useCallback((d: Dpe) => navigate(`/?dpe=${encodeURIComponent(d.number)}`), []);

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
                <div className="mb-6">
                    <h1 className="text-3xl sm:text-4xl text-ink">Carte de prospection</h1>
                    <p className="mt-2 text-muted max-w-3xl">
                        Les logements classés G, F ou E dont le DPE vient d'être réalisé : un DPE récent annonce souvent une vente ou une
                        location. Contactez ces propriétaires les premiers, avec une estimation et un plan de rénovation chiffré.
                    </p>
                    <div className="mt-5 inline-flex rounded-xl border border-line bg-raised p-1" role="tablist" aria-label="Que chercher">
                        {([['dpe', 'Logements à rénover'], ['immeubles', 'Immeubles entiers']] as const).map(([m, label]) => (
                            <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
                                className={`h-9 px-4 rounded-lg text-sm transition-colors ${mode === m ? 'bg-brass text-canvas font-medium' : 'text-muted hover:text-ink'}`}>
                                {label}
                            </button>
                        ))}
                    </div>
                    {mode === 'immeubles' && (
                        <p className="mt-3 text-sm text-muted max-w-3xl">
                            Les immeubles de 3 logements ou plus détenus en entier par une SCI ou une autre société privée, hors copropriété,
                            bailleurs sociaux et organismes publics : à vendre en bloc à un investisseur, ou lot par lot après découpe. La fiche
                            donne le siège de la société, ses dirigeants et ses autres immeubles.
                        </p>
                    )}
                </div>

                <div className="flex flex-col lg:flex-row gap-3 lg:items-center mb-4">
                    <form onSubmit={locate} className="flex flex-1 items-center rounded-xl border border-line bg-raised focus-within:border-brass/70">
                        <Search size={16} className="ml-3.5 text-faint" />
                        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Commune, quartier ou adresse"
                            className="w-full bg-transparent px-3 h-11 text-ink outline-none" aria-label="Commune ou adresse" />
                        <button type="button" onClick={aroundMe} disabled={locating} title="Autour de ma position"
                            className="mr-1.5 h-8 px-2.5 shrink-0 flex items-center gap-1.5 rounded-lg text-xs text-muted hover:text-ink hover:bg-panel">
                            {locating ? <Loader2 size={14} className="animate-spin" /> : <LocateFixed size={14} />}
                            <span className="hidden sm:inline">Autour de moi</span>
                        </button>
                    </form>
                    {mode === 'immeubles' ? (
                        <>
                            <select value={minLog} onChange={e => setMinLog(e.target.value)} aria-label="Nombre de logements"
                                className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                                <option value="3">3 logements ou plus</option>
                                <option value="5">5 logements ou plus</option>
                                <option value="10">10 logements ou plus</option>
                            </select>
                            <select value={monoDpe} onChange={e => setMonoDpe(e.target.value as 'all' | 'fg')} aria-label="DPE"
                                className="h-11 rounded-xl border border-line bg-raised px-3 text-sm text-ink">
                                <option value="all">Tous les DPE</option>
                                <option value="fg">DPE F ou G (location interdite)</option>
                            </select>
                        </>
                    ) : <>
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
                    </>}
                </div>

                <div className="grid lg:grid-cols-[1fr_380px] gap-4">
                    <div className="relative rounded-2xl overflow-hidden border border-line lg:self-start">
                        <div ref={containerRef} className="sprea-map h-[60vh] lg:h-[70vh] w-full" />
                        <div className="absolute top-3 left-3 right-16 z-[500] flex flex-wrap gap-2 pointer-events-none">
                            {zoom < MIN_ZOOM && (
                                <span className="rounded-lg border border-line bg-panel/90 backdrop-blur px-3 py-1.5 text-sm text-ink">Rapprochez-vous pour afficher les logements.</span>
                            )}
                            {zoom >= MIN_ZOOM && mode === 'immeubles' && mono && (
                                <span className="rounded-lg border border-line bg-panel/90 backdrop-blur px-3 py-1.5 text-sm text-ink tabular-nums">
                                    {mono.buildings.length.toLocaleString('fr-FR')} immeuble{mono.buildings.length > 1 ? 's' : ''}
                                    {mono.truncated ? ' · zone dense : zoomez pour tout voir' : framed ? ' · dans le cadre en pointillés' : ''}
                                </span>
                            )}
                            {zoom >= MIN_ZOOM && mode === 'dpe' && result && (
                                <span className="rounded-lg border border-line bg-panel/90 backdrop-blur px-3 py-1.5 text-sm text-ink tabular-nums">
                                    {result.dwellings.toLocaleString('fr-FR')} logement{result.dwellings > 1 ? 's' : ''} · {result.addresses.length.toLocaleString('fr-FR')} adresse{result.addresses.length > 1 ? 's' : ''}
                                    {result.truncated ? ' · zone dense : zoomez pour tout voir' : framed ? ' · dans le cadre en pointillés' : ''}
                                </span>
                            )}
                            {loading && <span className="rounded-lg border border-line bg-panel/90 backdrop-blur px-3 py-1.5 text-sm text-ink flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Chargement</span>}
                        </div>
                        <div className="absolute bottom-3 left-3 z-[500] flex items-center gap-3 rounded-lg border border-line bg-panel/90 backdrop-blur px-3 py-1.5 text-xs text-muted pointer-events-none">
                            {mode === 'immeubles' ? <>
                                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: NO_DPE_COLOR }} />sans DPE</span>
                                <span className="text-faint">· couleur : DPE</span>
                            </> : LABEL_OPTIONS.filter(l => labels.includes(l)).map(l => (
                                <span key={l} className="flex items-center gap-1.5">
                                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: DPE_COLORS[l].bg }} />{l}
                                </span>
                            ))}
                            {mode === 'dpe' && <span className="hidden sm:inline text-faint">· taille : nombre de logements</span>}
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
                        ) : mode === 'dpe' && result?.locked ? (
                            <Card className="p-5">
                                <p className="text-ink font-medium flex items-center gap-2"><Lock size={16} className="text-brass" />Adresses réservées aux abonnés</p>
                                <p className="mt-2 text-sm text-muted">
                                    {result.dwellings.toLocaleString('fr-FR')} logements classés {labels.join(', ')} dans cette zone.
                                    Avec l'abonnement : les adresses, le détail de chaque DPE, l'export CSV et un modèle de courrier par adresse.
                                </p>
                                <Button className="mt-4 w-full" onClick={() => navigate('/tarifs')}>Voir les formules</Button>
                            </Card>
                        ) : null}

                        {mode === 'immeubles' && mono && (
                            <Card className="p-0 overflow-hidden">
                                <div className="px-4 py-3 border-b border-line">
                                    <p className="text-sm text-ink font-medium">{mono.buildings.length.toLocaleString('fr-FR')} immeubles</p>
                                    <p className="text-xs text-faint">Les plus grands d'abord</p>
                                </div>
                                <MonoproList buildings={mono.buildings}
                                    onFocus={b => mapRef.current?.setView([b.lat, b.lon], Math.max(mapRef.current.getZoom(), 17))}
                                    onOpen={b => setSheet({ id: b.id })} />
                            </Card>
                        )}

                        {mode === 'dpe' && showDetails && (
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

                        {mode === 'dpe' && showDetails && (
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
                                                        {a.dpe![0].surface ? ` · ${Math.round(a.dpe![0].surface)} m²` : ''} · DPE du {formatDate(latestDate(a))}
                                                    </span>
                                                </span>
                                            </button>
                                            <div className="mt-2 ml-10 flex flex-wrap gap-3 text-xs">
                                                {isBuilding(a.dpe![0]) ? (
                                                    <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1"
                                                        onClick={() => setSheet({ near: { lat: a.lat, lon: a.lon, address: a.address || '' } })}>
                                                        <Building2 size={12} />Fiche immeuble et propriétaire
                                                    </button>
                                                ) : (
                                                    <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1" onClick={() => open(a.dpe![0])}>
                                                        <MapPin size={12} />Simuler la rénovation
                                                    </button>
                                                )}
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
                    Immeubles entiers : base nationale des bâtiments (CSTB, Licence Ouverte), propriétaires personnes morales (DGFiP), Annuaire des entreprises.
                    Les adresses s'utilisent dans le cadre de l'<Link to="/cgv" className="underline hover:text-ink">article 14 des CGV</Link> : origine des données
                    indiquée dans chaque courrier, oppositions respectées, pas de démarchage téléphonique.
                </p>
            </main>
            <SiteFooter />
            {letterFor && <LetterDialog target={letterFor} onClose={() => setLetterFor(null)} />}
            {sheet && <MonoproSheet target={sheet} onClose={() => setSheet(null)}
                onFocus={(lat, lon) => mapRef.current?.setView([lat, lon], Math.max(mapRef.current.getZoom(), 17))} />}
        </div>
    );
}
