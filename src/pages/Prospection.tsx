import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowLeft, ArrowRight, Bell, Building2, Calculator, Download, Eye, FileSearch, FileText, Flame, Loader2, Receipt, Route, Lock, MapPin, QrCode, Radar, Search, Star, UserSearch, Users, Workflow } from 'lucide-react';
import { useAccount } from '../account';
import { toProperty, type PropertyData } from '../model';
import { Link, navigate } from '../router';
import { useSeo } from '../seo';
import { TourHost, useAutoTour } from '../tour';
import { Button, DPE_COLORS, DpeBadge, eur, eurRange, type DPEClass } from '../ui';
import { AlertsPanel, type Zone } from './Alerts';
import { NeighbourLetterDialog, SIGNAL_COLORS, SalesPanel, SignalsPanel, TourPanel, loadTour, saveTour, titleCase,
    type SaleItem, type SalesResult, type SignalsResult, type TourStop } from './ProspectionTools';
import LetterDialog, { type LetterTarget } from './LetterDialog';
import OwnerRequestDialog, { type OwnerTarget } from './OwnerRequestDialog';
import { MonoproList, MonoproSheet, NO_DPE_COLOR, monoColor, type MonoBuilding, type SheetTarget } from './Monopro';
import { DossierDialog, FOLLOW_UPS, dpeAge, type Audience, type FollowUp, type Opportunity, type OpportunityScan } from './Opportunities';

// Prospection: the agent's one prospecting dashboard. The radar of their area
// (recent F and G DPE, each valued) with the targets ranked by score, every
// recent DPE of the visible map, the whole buildings owned by companies, one
// target with every figure and every action, and the follow-up board with
// what is due today. Built only on SPREA's data: nothing here is made up.

type View = 'radar' | 'signaux' | 'dpe' | 'immeubles' | 'ventes' | 'alertes' | 'fiche' | 'tournee' | 'cible' | 'suivi';
interface Center { lat: number; lon: number; label: string }
interface PipelineItem { number: string; status: FollowUp; address: string | null; updated_at: string | null; mine: boolean }
interface EstimateLead { id: string; name: string; address: string; city: string | null; lat: number | null; lon: number | null; project: string; status: string; phone: string | null; created_at: string }
interface Kpis { newDpe: number | null; signals: number | null; strongSignals: number | null }
interface Dpe { number: string; label: DPEClass; kind: string | null; surface: number | null; date: string | null; period: string | null; detail: string | number | null }
interface Address { address?: string; lat: number; lon: number; worst: DPEClass; dpe?: Dpe[]; count?: number }
interface DpeResult { locked: boolean; addresses: Address[]; dwellings: number; total: number; truncated: boolean }

// Every recent DPE and the whole buildings follow the visible map: below this
// zoom the area would only be a dot; the server accepts 0.045° a side
const MIN_ZOOM = 12;
const MAX_SPAN = 0.044;
const LABEL_OPTIONS: DPEClass[] = ['G', 'F', 'E'];
const KINDS = [{ value: '', label: 'Tous les biens' }, { value: 'maison', label: 'Maisons' }, { value: 'appartement', label: 'Appartements' }];
const SINCE = [
    { value: '7', label: '7 derniers jours' }, { value: '31', label: 'Dernier mois' }, { value: '92', label: '3 derniers mois' },
    { value: '183', label: '6 derniers mois' }, { value: '365', label: '12 derniers mois' },
];
const daysAgoIso = (days: string) => new Date(Date.now() - Number(days) * 86400000).toISOString().slice(0, 10);
const latestDate = (a: Address) => (a.dpe || []).reduce((m, d) => (d.date && d.date > m ? d.date : m), '');
// A whole building's DPE leads to the building sheet, not to the simulator of a dwelling
const isBuilding = (d: Dpe) => (d.kind || '').toLowerCase() === 'immeuble';
const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('fr-FR') : '');

// The visible map, reduced around its center when larger than the server limit
function searchArea(map: L.Map): { key: string; clamped: boolean; bounds: L.LatLngBounds } {
    const b = map.getBounds();
    const c = map.getCenter();
    let [w, s, e, n] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    let clamped = false;
    if (e - w > MAX_SPAN) { w = c.lng - MAX_SPAN / 2; e = c.lng + MAX_SPAN / 2; clamped = true; }
    if (n - s > MAX_SPAN) { s = c.lat - MAX_SPAN / 2; n = c.lat + MAX_SPAN / 2; clamped = true; }
    return { key: [w, s, e, n].map(v => v.toFixed(4)).join(','), clamped, bounds: L.latLngBounds([s, w], [n, e]) };
}

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

const RADIUS_M = 1500;
const CENTER_KEY = 'sprea-command-center';
const GOAL_KEY = 'sprea-command-goal';
const DEFAULT_CENTER: Center = { lat: 50.6329, lon: 3.0573, label: 'Lille' };
// A letter unanswered after this many days calls for a reminder
const REMIND_DAYS = 14;
const TILES = 'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2'
    + '&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}';
const STAGES: { value: FollowUp; label: string }[] = [
    { value: 'courrier', label: 'Courrier envoyé' },
    { value: 'relance', label: 'Relance' },
    { value: 'rendez_vous', label: 'Rendez-vous' },
    { value: 'mandat', label: 'Mandat' },
];
const PROJECTS: Record<string, string> = { vendre_3m: 'vendre sous 3 mois', vendre_12m: 'vendre dans l\'année', reflexion: 'en réflexion', curiosite: 'par curiosité' };

// The area scanned: 1.5 km around the center, within the server's limit (0.045°)
function bbox(c: Center): string {
    const dlat = RADIUS_M / 111320;
    const dlon = Math.min(0.022, RADIUS_M / (111320 * Math.cos((c.lat * Math.PI) / 180)));
    return [c.lon - dlon, c.lat - dlat, c.lon + dlon, c.lat + dlat].map(v => v.toFixed(4)).join(',');
}
const daysSince = (iso: string | null) => (iso ? (Date.now() - new Date(iso).getTime()) / 86400000 : Infinity);
const firstName = (name?: string | null) => (name || '').trim().split(/\s+/)[0] || '';
const esc = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
const shortAddress = (a: string) => a.replace(/\s+\d{5}\s+.*$/, '');

// Score out of 100: what the renovation adds to the value (40), how recent the
// DPE is (35: a new DPE usually announces a sale or a letting), and how urgent
// the works are for the owner (25: letting already banned, or soon)
export function score(o: Opportunity): number {
    const created = Math.max(0, Math.min(1, (o.value_created || 0) / (0.15 * (o.price || 1))));
    const age = daysSince(o.dpe_date) / 30.4;
    const fresh = age <= 1 ? 1 : age >= 24 ? 0 : 1 - (age - 1) / 23;
    const rental = (o.rental_now || '').toLowerCase();
    const urgency = rental.includes('interdite') ? 1 : rental.includes('jusqu') ? 0.6 : 0.2;
    return Math.max(1, Math.min(99, Math.round(40 * created + 35 * fresh + 25 * urgency)));
}

function tags(o: Opportunity, status?: FollowUp): { text: string; tone: 'y' | 'r' | 's' | '' }[] {
    const out: { text: string; tone: 'y' | 'r' | 's' | '' }[] = [{ text: dpeAge(o.dpe_date), tone: daysSince(o.dpe_date) < 62 ? 'y' : '' }];
    const rental = (o.rental_now || '').toLowerCase();
    if (rental.includes('interdite')) out.push({ text: 'Location interdite', tone: 'r' });
    else if (rental.includes('jusqu')) out.push({ text: o.rental_now.replace(/^Louable /, 'Louable '), tone: 'r' });
    if (o.value_created > 0) out.push({ text: `+${eur(o.value_created)} créés`, tone: 's' });
    if (status) out.push({ text: FOLLOW_UPS.find(f => f.value === status)?.label || status, tone: '' });
    return out;
}

const TONES = { y: 'text-brass-light bg-brass/10', r: 'text-[#F2A08C] bg-coral/10', s: 'text-sage bg-sage/10', '': 'text-muted bg-raised' };

function Ring({ value, size = 42 }: { value: number; size?: number }) {
    const r = size / 2 - 4;
    const c = 2 * Math.PI * r;
    return (
        <span className="relative shrink-0" style={{ width: size, height: size }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                <circle cx={size / 2} cy={size / 2} r={r} stroke="#25324C" strokeWidth="3.5" fill="none" />
                <circle cx={size / 2} cy={size / 2} r={r} stroke="#C9A45C" strokeWidth="3.5" fill="none" strokeLinecap="round"
                    strokeDasharray={`${(c * value) / 100} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-[13px] font-semibold text-ink tabular-nums">{value}</span>
        </span>
    );
}

const Badge = ({ label }: { label: DPEClass }) => (
    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] text-[11px] font-bold"
        style={{ backgroundColor: DPE_COLORS[label].bg, color: DPE_COLORS[label].fg }}>{label}</span>
);
const Kbd = ({ children }: { children: React.ReactNode }) => (
    <kbd className="whitespace-nowrap rounded-[5px] border border-line bg-panel px-1.5 py-px text-[11px] font-sans text-muted">{children}</kbd>
);

function Orb() {
    return <span className="cmd-orb h-10 w-10 shrink-0 rounded-full" aria-hidden />;
}

export default function ProspectionPage() {
    useSeo({ title: 'Prospection · SPREA', noindex: true });
    const { session, me, authedFetch, openLogin, config } = useAccount();
    // A link may ask for a view: ?mode=dpe, ?mode=immeubles, or one building
    // from the simulator (?immeuble=lat,lon&adresse=...)
    const params = useRef(new URLSearchParams(window.location.search));
    const linked = useRef((() => {
        const [lat, lon] = (params.current.get('immeuble') || '').split(',').map(Number);
        return Number.isFinite(lat) && Number.isFinite(lon) && params.current.get('immeuble')
            ? { lat, lon, address: params.current.get('adresse') || '' } : null;
    })());
    const [view, setView] = useState<View>(() => {
        const mode = params.current.get('mode');
        if (linked.current || mode === 'immeubles') return 'immeubles';
        return (['dpe', 'alertes', 'fiche', 'signaux', 'ventes', 'tournee'] as const).find(m => m === mode) || 'radar';
    });
    const [center, setCenter] = useState<Center | null>(() => {
        if (linked.current) return { lat: linked.current.lat, lon: linked.current.lon, label: 'Immeuble' };
        try { return JSON.parse(sessionStorage.getItem(CENTER_KEY) || 'null'); } catch { return null; }
    });
    const [sheet, setSheet] = useState<SheetTarget | null>(() => (linked.current ? { near: linked.current } : null));
    // Every recent DPE of the visible map
    const [labels, setLabels] = useState<DPEClass[]>(['G', 'F']);
    const [kind, setKind] = useState('');
    const [since, setSince] = useState('183');
    const [dpe, setDpe] = useState<DpeResult | null>(null);
    const [alertMessage, setAlertMessage] = useState<string | null>(null);
    // Whole buildings owned by companies
    const [minLog, setMinLog] = useState('3');
    const [monoDpe, setMonoDpe] = useState<'all' | 'fg'>('all');
    const [monoSignal, setMonoSignal] = useState<'all' | 'any' | 'strong'>('all');
    const [mono, setMono] = useState<{ buildings: MonoBuilding[]; truncated: boolean } | null>(null);
    const [layerLoading, setLayerLoading] = useState(false);
    // Daily alerts: zones drawn on the map, list reloaded once a zone is created
    const [alertZones, setAlertZones] = useState<Zone[]>([]);
    const [alertsReload, setAlertsReload] = useState(0);
    // Who is likely to sell, the sales of the area, the letterbox round
    const [signalsData, setSignalsData] = useState<SignalsResult | null>(null);
    const [signalFilter, setSignalFilter] = useState<'all' | 'fort' | 'held' | 'fresh'>('all');
    const [salesData, setSalesData] = useState<SalesResult | null>(null);
    const [salesMonths, setSalesMonths] = useState(12);
    const [toolLoading, setToolLoading] = useState(false);
    const [tour, setTour] = useState<TourStop[]>(loadTour);
    const [neighbourFor, setNeighbourFor] = useState<SaleItem | null>(null);
    const salesRef = useRef<SaleItem[]>([]);
    const addStop = useCallback((st: TourStop) => setTour(t => (t.some(x => x.key === st.key) ? t : [...t, st])), []);
    const addStopRef = useRef(addStop);
    const inTour = (key: string) => tour.some(x => x.key === key);
    useEffect(() => saveTour(tour), [tour]);
    // One dwelling looked up by address or DPE number
    const [fiche, setFiche] = useState<{ results: PropertyData[]; loading: boolean; error: string | null }>({ results: [], loading: false, error: null });
    const [scan, setScan] = useState<OpportunityScan | null>(null);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [kpis, setKpis] = useState<Kpis>({ newDpe: null, signals: null, strongSignals: null });
    const [pipeline, setPipeline] = useState<PipelineItem[]>([]);
    const [leads, setLeads] = useState<EstimateLead[]>([]);
    const [agentName, setAgentName] = useState('');
    const [sortBy, setSortBy] = useState<'score' | 'fresh' | 'value' | 'todo'>('score');
    const [selected, setSelected] = useState<string | null>(null);
    const [letterFor, setLetterFor] = useState<LetterTarget | null>(null);
    const [ownerFor, setOwnerFor] = useState<OwnerTarget | null>(null);
    const [dossier, setDossier] = useState<{ o: Opportunity; audience: Audience } | null>(null);
    const [goal, setGoal] = useState(() => Number(localStorage.getItem(GOAL_KEY)) || 5);
    const [moved, setMoved] = useState(false);

    const pro = !!me?.is_pro;
    // First visit straight to Prospection: the welcome tour from its first steps
    useAutoTour('command', pro, 1);
    const statuses = useMemo(() => Object.fromEntries(pipeline.map(p => [p.number, p.status])) as Record<string, FollowUp>, [pipeline]);

    // Where to start: the last area, else the visitor's town (from their IP address)
    useEffect(() => {
        if (center) return;
        fetch('/api/geo').then(r => (r.ok ? r.json() : null)).catch(() => null).then(geo => {
            setCenter(geo?.lat != null ? { lat: geo.lat, lon: geo.lon, label: geo.city || 'Votre secteur' } : DEFAULT_CENTER);
        });
    }, [center]);
    useEffect(() => {
        if (center) try { sessionStorage.setItem(CENTER_KEY, JSON.stringify(center)); } catch { /* private mode */ }
    }, [center]);

    // Everything around the center
    const load = useCallback(async (c: Center) => {
        const box = bbox(c);
        setScanning(true);
        setError(null);
        setScan(null);
        setSelected(null);
        setMoved(false);
        const since = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
        const side = Promise.allSettled([
            authedFetch(`/api/prospection?bbox=${box}&labels=G,F,E&since=${since}`).then(r => (r.ok ? r.json() : null)),
            authedFetch(`/api/monopro?bbox=${box}&owner=company&min_log=3&dpe=all&signal=any`).then(r => (r.ok ? r.json() : null)),
        ]).then(([dpe, mono]) => {
            const d = dpe.status === 'fulfilled' ? dpe.value : null;
            const m = mono.status === 'fulfilled' ? mono.value : null;
            const flagged = (m?.buildings || []).filter((b: { signal_level: string | null }) => b.signal_level && b.signal_level !== 'faible');
            setKpis({ newDpe: d ? d.dwellings : null, signals: m ? flagged.length : null,
                strongSignals: m ? flagged.filter((b: { signal_level: string }) => b.signal_level === 'fort').length : null });
        });
        try {
            const res = await authedFetch(`/api/opportunities?bbox=${box}&labels=E,F,G&profile=bailleur&sort=potentiel`);
            if (!res.ok) {
                const detail = await res.json().catch(() => ({}));
                throw new Error(res.status === 429 ? 'Trop de recherches : patientez une minute.' : detail.detail || "L'analyse a échoué.");
            }
            setScan(await res.json());
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setScanning(false);
        }
        await side;
    }, [authedFetch]);

    const loadBoard = useCallback(async () => {
        const [p, l, a] = await Promise.allSettled([
            authedFetch('/api/prospect-status/all').then(r => (r.ok ? r.json() : { items: [] })),
            authedFetch('/api/estimate-leads').then(r => (r.ok ? r.json() : { leads: [] })),
            authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {})) as Promise<{ agent_name?: string | null }>,
        ]);
        if (p.status === 'fulfilled') setPipeline(p.value.items || []);
        if (l.status === 'fulfilled') setLeads(l.value.leads || []);
        if (a.status === 'fulfilled') setAgentName(firstName(a.value.agent_name));
    }, [authedFetch]);

    useEffect(() => { if (pro && center) load(center); }, [pro, center, load]);
    useEffect(() => { if (pro) loadBoard(); }, [pro, loadBoard]);

    const targets = useMemo(() => {
        const items = (scan?.items || []).map(o => ({ o, score: score(o) }));
        const sorted = sortBy === 'fresh' ? items.sort((a, b) => (b.o.dpe_date || '').localeCompare(a.o.dpe_date || ''))
            : sortBy === 'value' ? items.sort((a, b) => b.o.value_created - a.o.value_created)
            : items.sort((a, b) => b.score - a.score);
        return sortBy === 'todo' ? sorted.filter(t => !statuses[t.o.number]) : sorted;
    }, [scan, sortBy, statuses]);
    const ranked = useMemo(() => [...(scan?.items || [])].map(o => ({ o, score: score(o) })).sort((a, b) => b.score - a.score), [scan]);
    const current = ranked.find(t => t.o.number === selected) || null;
    const rank = (n: string) => ranked.findIndex(t => t.o.number === n) + 1;

    const due = useMemo(() => pipeline.filter(p => (p.status === 'courrier' || p.status === 'relance') && daysSince(p.updated_at) >= REMIND_DAYS), [pipeline]);
    const newLeads = leads.filter(l => l.status === 'new');
    const monthStart = new Date(new Date().getFullYear(), new Date().getMonth(), 1).getTime();
    const won = pipeline.filter(p => (p.status === 'rendez_vous' || p.status === 'mandat') && p.updated_at && new Date(p.updated_at).getTime() >= monthStart).length;
    const counts = Object.fromEntries(STAGES.map(s => [s.value, pipeline.filter(p => p.status === s.value).length])) as Record<FollowUp, number>;
    const toContact = ranked.filter(t => !statuses[t.o.number]);
    const unlocked = (scan?.items || []).reduce((s, o) => s + Math.max(0, o.value_created), 0);

    const setStatus = async (o: { number: string; address: string }, status: FollowUp | '') => {
        const before = pipeline;
        setPipeline(list => {
            const rest = list.filter(p => p.number !== o.number);
            return status ? [{ number: o.number, status, address: o.address, updated_at: new Date().toISOString(), mine: true }, ...rest] : rest;
        });
        try {
            const res = await authedFetch('/api/prospect-status', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ number: o.number, status: status || null, address: o.address }),
            });
            if (!res.ok) throw new Error();
        } catch {
            setPipeline(before);
            setError("Le suivi n'a pas pu être enregistré, réessayez.");
        }
    };

    // --- Map ---
    // The map's container only exists once the account is known (the page
    // shows a gate before): the map is created when the container appears
    const [mapEl, setMapEl] = useState<HTMLDivElement | null>(null);
    const [mapReady, setMapReady] = useState(false);
    const centerRef = useRef(center);
    centerRef.current = center;
    const mapRef = useRef<L.Map | null>(null);
    const layer = useRef<L.LayerGroup | null>(null);
    const [radar, setRadar] = useState<{ x: number; y: number; r: number } | null>(null);
    const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
    const [area, setArea] = useState<{ key: string; clamped: boolean } | null>(null);
    const [zoom, setZoom] = useState(14.5);
    const dpeMarkers = useRef(new Map<string, L.CircleMarker>());

    useEffect(() => {
        const start = centerRef.current;
        if (!mapEl || !start) return;
        const map = L.map(mapEl, { zoomControl: false, preferCanvas: false, zoomSnap: 0.25, attributionControl: true })
            .setView([start.lat, start.lon], 14.5);
        L.control.zoom({ position: 'topright' }).addTo(map);
        L.tileLayer(TILES, { maxZoom: 19, minZoom: 6, attribution: '© IGN, DPE ADEME, DVF', className: 'sprea-tiles' }).addTo(map);
        layer.current = L.layerGroup().addTo(map);
        mapRef.current = map;
        setMapReady(true);
        const moved = () => { setZoom(map.getZoom()); const a = searchArea(map); setArea({ key: a.key, clamped: a.clamped }); };
        moved();
        map.on('moveend', moved);
        // Actions in the DPE popups (plain HTML, built by Leaflet)
        map.on('popupopen', e => {
            e.popup.getElement()?.querySelectorAll<HTMLElement>('[data-action]').forEach(el => {
                el.onclick = ev => {
                    ev.preventDefault();
                    const d = el.dataset;
                    if (d.action === 'simulate') navigate(`/?dpe=${encodeURIComponent(d.dpe || '')}`);
                    else if (d.action === 'building') setSheet({ near: { lat: Number(d.lat), lon: Number(d.lon), address: d.address || '' } });
                    else if (d.action === 'owner') setOwnerFor({ address: d.address || '', lat: Number(d.lat), lon: Number(d.lon) });
                    else if (d.action === 'tour') {
                        addStopRef.current({ key: `${d.lat},${d.lon}`, address: d.address || '', lat: Number(d.lat), lon: Number(d.lon),
                            label: (d.label || null) as DPEClass | null, dpeNumber: d.dpe || null });
                        el.textContent = 'Dans la tournée';
                    }
                    else if (d.action === 'neighbours') { const sale = salesRef.current[Number(d.idx)]; if (sale) setNeighbourFor(sale); }
                    else setLetterFor({ address: d.address || '', label: d.label as DPEClass, dpeNumber: d.dpe || '' });
                };
            });
        });
        const ro = new ResizeObserver(() => { map.invalidateSize(); setSize({ w: mapEl.clientWidth, h: mapEl.clientHeight }); });
        ro.observe(mapEl);
        return () => { ro.disconnect(); map.remove(); mapRef.current = null; layer.current = null; setMapReady(false); };
    }, [mapEl, !!center]); // eslint-disable-line react-hooks/exhaustive-deps

    // Radar rings follow the scanned circle on screen
    useEffect(() => {
        const map = mapRef.current;
        if (!map || !center) return;
        const place = () => {
            const p = map.latLngToContainerPoint([center.lat, center.lon]);
            const edge = map.latLngToContainerPoint(L.latLng(center.lat, center.lon).toBounds(RADIUS_M * 2).getNorthEast());
            setRadar({ x: p.x, y: p.y, r: Math.abs(edge.y - p.y) });
            setMoved(map.getCenter().distanceTo([center.lat, center.lon]) > 900 && map.getZoom() < 17);
        };
        place();
        map.on('move zoom resize', place);
        return () => { map.off('move zoom resize', place); };
    }, [center, mapReady]);

    // Every recent DPE / whole buildings of the visible map; moving inside
    // the area already loaded needs no new search
    const zoomOk = zoom >= MIN_ZOOM;
    const loadedDpe = useRef<{ box: number[]; filters: string } | null>(null);
    const loadedMono = useRef<{ box: number[]; filters: string } | null>(null);
    useEffect(() => {
        if ((view !== 'dpe' && view !== 'immeubles') || !pro || !zoomOk || !area) return;
        const box = area.key.split(',').map(Number);
        const filters = view === 'dpe' ? [labels.join(','), kind, since].join('|') : [minLog, monoDpe, monoSignal].join('|');
        const last = view === 'dpe' ? loadedDpe.current : loadedMono.current;
        if (view === 'dpe' && !labels.length) return;
        if (last && last.filters === filters && box[0] >= last.box[0] && box[1] >= last.box[1] && box[2] <= last.box[2] && box[3] <= last.box[3]) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            setLayerLoading(true);
            setError(null);
            try {
                const q = view === 'dpe'
                    ? new URLSearchParams({ bbox: area.key, labels: labels.join(','), since: daysAgoIso(since), ...(kind ? { kind } : {}) })
                    : new URLSearchParams({ bbox: area.key, owner: 'company', min_log: minLog, dpe: monoDpe, signal: monoSignal });
                const res = await authedFetch(`/api/${view === 'dpe' ? 'prospection' : 'monopro'}?${q}`, { signal: controller.signal });
                if (!res.ok) {
                    const detail = await res.json().catch(() => ({}));
                    throw new Error(res.status === 429 ? 'Trop de recherches : patientez une minute.' : detail.detail || 'La recherche a échoué.');
                }
                const data = await res.json();
                // A truncated result is only the start of a dense area: search again on any move
                const mark = data.truncated ? null : { box, filters };
                if (view === 'dpe') { loadedDpe.current = mark; setDpe(data); } else { loadedMono.current = mark; setMono(data); }
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setError((e as Error).message);
            } finally {
                setLayerLoading(false);
            }
        }, 450);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [view, pro, zoomOk, area, labels, kind, since, minLog, monoDpe, monoSignal, authedFetch]);
    const dpeList = useMemo(() => (dpe && !dpe.locked ? [...dpe.addresses].sort((a, b) => latestDate(b).localeCompare(latestDate(a))) : []), [dpe]);

    // Daily alert on the visible area (center, radius up to 3 km)
    const createAlert = async () => {
        const map = mapRef.current;
        if (!map) return;
        const c = map.getCenter();
        const radius = Math.round(Math.min(3000, Math.max(200, c.distanceTo(map.getBounds().getNorthEast()))));
        const name = (center?.label && center.label !== 'Secteur choisi' ? center.label : 'Ma zone').slice(0, 60);
        setAlertMessage(null);
        try {
            const res = await authedFetch('/api/alerts/zones', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, lat: c.lat, lon: c.lng, radius_m: radius, labels: labels.length ? labels : ['E', 'F', 'G'], kind: kind || null }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || "L'alerte n'a pas pu être créée.");
            setAlertMessage(`Alerte « ${name} » créée : ${data.new_hits} DPE reçus ces 14 derniers jours. Les nouveaux arriveront chaque matin.`);
            setAlertsReload(n => n + 1);
        } catch (e) {
            setAlertMessage((e as Error).message);
        }
    };
    const exportCsv = () => {
        const blob = new Blob(['\ufeff' + toCsv(dpeList)], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'prospection-dpe.csv';
        link.click();
        URL.revokeObjectURL(url);
    };
    const focusAddress = (a: Address) => {
        mapRef.current?.setView([a.lat, a.lon], Math.max(mapRef.current.getZoom(), 17));
        setTimeout(() => dpeMarkers.current.get(a.address || `${a.lat},${a.lon}`)?.openPopup(), 300);
    };
    const showMap = (v: View) => { setView(v); setSelected(null); };

    // Signals and sales of the visible map, loaded once per area
    const loadedTool = useRef<Record<string, string>>({});
    useEffect(() => {
        if ((view !== 'signaux' && view !== 'ventes') || !pro || !zoomOk || !area) return;
        const key = view === 'signaux' ? area.key : `${area.key}|${salesMonths}`;
        if (loadedTool.current[view] === key) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            setToolLoading(true);
            setError(null);
            try {
                const res = await authedFetch(view === 'signaux' ? `/api/signals?bbox=${area.key}` : `/api/sales?bbox=${area.key}&months=${salesMonths}`,
                    { signal: controller.signal });
                if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Le chargement a échoué.');
                const data = await res.json();
                loadedTool.current[view] = key;
                if (view === 'signaux') setSignalsData(data);
                else { salesRef.current = data.sales; setSalesData(data); }
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setError((e as Error).message);
            } finally {
                setToolLoading(false);
            }
        }, 600);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [view, pro, zoomOk, area, salesMonths, authedFetch]);
    const delivered = async (stops: TourStop[]) => {
        for (const st of stops) if (st.dpeNumber) await setStatus({ number: st.dpeNumber, address: st.address }, 'courrier');
        setTour(t => t.filter(x => !stops.some(st => st.key === x.key)));
    };
    // Opening the round frames its stops
    useEffect(() => {
        if (view !== 'tournee' || !tour.length || !mapRef.current) return;
        mapRef.current.fitBounds(L.latLngBounds(tour.map(t => L.latLng(t.lat, t.lon))), { padding: [60, 60], maxZoom: 17 });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [view]);
    // Opening the alerts frames their zones, once per visit of the view
    const framed = useRef(false);
    useEffect(() => {
        if (view !== 'alertes') { framed.current = false; return; }
        const zs = alertZones.filter(z => z.lat != null && z.lon != null);
        if (framed.current || !zs.length || !mapRef.current) return;
        framed.current = true;
        const bounds = L.latLngBounds(zs.map(z => L.latLng(z.lat, z.lon).toBounds(z.radius_m * 2)).flatMap(b => [b.getSouthWest(), b.getNorthEast()]));
        mapRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
    }, [view, alertZones]);
    const searchFiche = async (query: string) => {
        const q = query.trim();
        if (!q) return;
        // A DPE number: 13 letters and digits, the year first (2659E…)
        const byNumber = /^[0-9]{4}[A-Z0-9]{9}$/i.test(q.replace(/\s/g, ''));
        setFiche({ results: [], loading: true, error: null });
        try {
            const res = await authedFetch(byNumber ? `/api/search-dpe/${encodeURIComponent(q.replace(/\s/g, '').toUpperCase())}` : `/api/search-address?q=${encodeURIComponent(q)}`);
            if (res.status === 429) throw new Error('Trop de recherches en peu de temps : patientez une minute.');
            if (!res.ok) throw new Error('La recherche a échoué.');
            const data = await res.json();
            const results: PropertyData[] = (data.results || []).map(toProperty);
            setFiche({ results, loading: false, error: results.length ? null : data.error ? "Le service de l'ADEME ne répond pas pour le moment."
                : byNumber ? 'Aucun DPE ne correspond à ce numéro.' : "Aucun DPE trouvé à cette adresse : essayez le numéro du DPE." });
            const first = results.find(r => r.latitude != null && r.longitude != null);
            if (first) mapRef.current?.flyTo([first.latitude!, first.longitude!], 17, { duration: 0.8 });
        } catch (e) {
            setFiche({ results: [], loading: false, error: (e as Error).message });
        }
    };

    const focus = useCallback((o: Opportunity) => {
        setSelected(o.number);
        setView('cible');
        mapRef.current?.flyTo([o.lat, o.lon], 18, { duration: 0.9 });
    }, []);
    const backToRadar = useCallback(() => {
        setView('radar');
        if (center) mapRef.current?.flyTo([center.lat, center.lon], 14.5, { duration: 0.8 });
    }, [center]);

    // Markers: every target, the five best behind a reticle
    useEffect(() => {
        const group = layer.current;
        if (!group) return;
        group.clearLayers();
        dpeMarkers.current.clear();
        if (view === 'dpe') {
            if (!dpe || !zoomOk) return;
            const link = 'color:#E3C98F;font-weight:600;text-decoration:none;cursor:pointer';
            for (const a of dpe.addresses) {
                const n = a.dpe?.length ?? a.count ?? 1;
                const marker = L.circleMarker([a.lat, a.lon], {
                    radius: Math.min(14, 4.5 + Math.sqrt(n) * 2), color: '#0A0F1A', weight: 1.5, opacity: 0.9, fillColor: DPE_COLORS[a.worst].bg, fillOpacity: 0.95,
                });
                if (!dpe.locked && a.dpe) {
                    const lines = a.dpe.slice(0, 8).map(d =>
                        `<li style="margin:3px 0"><b style="color:${DPE_COLORS[d.label].bg}">${d.label}</b> · ${esc(d.kind || 'Logement')}`
                        + `${d.surface ? ` · ${Math.round(d.surface)} m²` : ''}${d.detail ? ` · ${esc(String(d.detail))}` : ''}`
                        + ` <span style="color:#97A1B3">(${formatDate(d.date)})</span>`
                        + (isBuilding(d) ? ` · <a href="#" data-action="building" data-lat="${a.lat}" data-lon="${a.lon}" data-address="${esc(a.address || '')}" style="${link}">Fiche immeuble</a>`
                            : d.number ? ` · <a href="#" data-action="simulate" data-dpe="${esc(d.number)}" style="${link}">Simuler</a>` : '')
                        + '</li>').join('');
                    const first = a.dpe[0];
                    marker.bindPopup(`<b>${esc(a.address || '')}</b><ul style="margin:6px 0 0;padding-left:16px">${lines}</ul>`
                        + (a.dpe.length > 8 ? `<div style="color:#97A1B3">+ ${a.dpe.length - 8} autres</div>` : '')
                        + (first?.number ? `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #25324C"><a href="#" data-action="letter"`
                            + ` data-dpe="${esc(first.number)}" data-address="${esc(a.address || '')}" data-label="${a.worst}" style="${link}">Courrier avec QR code</a>`
                            + ` · <a href="#" data-action="owner" data-lat="${a.lat}" data-lon="${a.lon}" data-address="${esc(a.address || '')}" style="${link}">Connaître le propriétaire</a></div>` : ''),
                        { minWidth: 260 });
                    dpeMarkers.current.set(a.address || `${a.lat},${a.lon}`, marker);
                } else {
                    marker.bindTooltip(`${n} logement${n > 1 ? 's' : ''} classé${n > 1 ? 's' : ''} ${a.worst}`);
                }
                marker.addTo(group);
            }
            return;
        }
        if (view === 'signaux') {
            if (!signalsData || !zoomOk) return;
            const link = 'color:#E3C98F;font-weight:600;text-decoration:none;cursor:pointer';
            for (const it of [...signalsData.items].reverse()) {
                const shown = signalFilter === 'all' || (signalFilter === 'fort' ? it.level === 'fort' : signalFilter === 'held' ? it.long_held
                    : it.reasons.some(r => r.kind === 'dpe' && r.points >= 28));
                if (!shown) continue;
                const reasons = it.reasons.map(r => `<li style="margin:2px 0"><b style="color:${r.points < 0 ? '#FF6B4A' : '#E3C98F'}">${r.points > 0 ? '+' : ''}${r.points}</b> ${esc(r.label)}</li>`).join('');
                const data = `data-lat="${it.lat}" data-lon="${it.lon}" data-address="${esc(it.address)}" data-dpe="${esc(it.dpe_number || '')}" data-label="${it.label || ''}"`;
                L.circleMarker([it.lat, it.lon], { radius: 4 + it.score / 12, color: '#0A0F1A', weight: 1.5, fillColor: SIGNAL_COLORS[it.level], fillOpacity: 0.9 })
                    .bindPopup(`<b>${esc(it.address)}</b><div style="margin-top:2px;color:${SIGNAL_COLORS[it.level]}">Probabilité de vente : ${it.score}/100</div>`
                        + `<ul style="margin:6px 0 0;padding-left:14px">${reasons}</ul>`
                        + `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #25324C"><a href="#" data-action="tour" ${data} style="${link}">${inTour(`${it.lat},${it.lon}`) ? 'Dans la tournée' : 'Ajouter à la tournée'}</a>`
                        + (it.dpe_number && it.label ? ` · <a href="#" data-action="letter" data-dpe="${esc(it.dpe_number)}" data-address="${esc(it.address)}" data-label="${it.label}" style="${link}">Courrier</a>` : '')
                        + ` · <a href="#" data-action="owner" ${data} style="${link}">Propriétaire</a></div>`, { minWidth: 280 })
                    .addTo(group);
            }
            return;
        }
        if (view === 'ventes') {
            if (!salesData || !zoomOk) return;
            const link = 'color:#E3C98F;font-weight:600;text-decoration:none;cursor:pointer';
            salesData.sales.forEach((sl, i) => {
                L.circleMarker([sl.lat, sl.lon], { radius: 6, color: '#E3C98F', weight: 2, fillColor: '#0D1424', fillOpacity: 0.9 })
                    .bindPopup(`<b>${esc(sl.street ? titleCase(sl.street) : 'Adresse non publiée')}</b><br>${esc(sl.kind)} · ${Math.round(sl.surface)} m² · ${formatDate(sl.date)}`
                        + `<br><b>${eur(sl.price)}</b> · ${eur(sl.price_m2)} /m²`
                        + `<div style="margin-top:8px;padding-top:6px;border-top:1px solid #25324C"><a href="#" data-action="neighbours" data-idx="${i}" style="${link}">Courrier aux voisins</a></div>`)
                    .addTo(group);
            });
            return;
        }
        if (view === 'tournee') {
            if (tour.length > 1) L.polyline(tour.map(t => [t.lat, t.lon] as [number, number]), { color: '#C9A45C', weight: 3, opacity: 0.85, dashArray: '6 6' }).addTo(group);
            tour.forEach((t, i) => {
                L.marker([t.lat, t.lon], { icon: L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13],
                    html: `<div style="width:26px;height:26px;border-radius:50%;background:#0D1424;border:2px solid #E3C98F;color:#E3C98F;font:600 12px Inter,sans-serif;display:flex;align-items:center;justify-content:center">${i + 1}</div>` }) })
                    .bindTooltip(esc(t.address)).addTo(group);
            });
            return;
        }
        if (view === 'alertes') {
            for (const z of alertZones) {
                if (z.lat == null || z.lon == null) continue;
                L.circle([z.lat, z.lon], { radius: z.radius_m, color: '#E3C98F', weight: z.active ? 2 : 1, dashArray: z.active ? undefined : '4 6',
                    fillColor: '#C9A45C', fillOpacity: z.active ? 0.12 : 0.04 })
                    .bindTooltip(`${esc(z.name)} · ${z.radius_m >= 1000 ? `${(z.radius_m / 1000).toFixed(1).replace('.', ',')} km` : `${z.radius_m} m`}${z.active ? '' : ' · en pause'}`)
                    .addTo(group);
            }
            return;
        }
        if (view === 'fiche') {
            for (const r of fiche.results) {
                if (r.latitude == null || r.longitude == null || !r.label) continue;
                L.circleMarker([r.latitude, r.longitude], { radius: 9, color: '#0A0F1A', weight: 1.5, fillColor: DPE_COLORS[r.label as DPEClass]?.bg || '#97A1B3', fillOpacity: 0.95 })
                    .bindTooltip(`${esc(r.address || '')} · DPE ${r.label}`).addTo(group);
            }
            return;
        }
        if (view === 'immeubles') {
            if (!mono || !zoomOk) return;
            for (const b of mono.buildings) {
                L.circleMarker([b.lat, b.lon], {
                    radius: Math.min(16, 4 + Math.sqrt(b.nb_log) * 2),
                    // Gold outline: owned by a company (owner identified); red: sale signal
                    color: b.signal_level === 'fort' ? '#FF6B4A' : b.owner ? '#E3C98F' : '#0A0F1A',
                    weight: b.signal_level === 'fort' || b.signal_level === 'moyen' ? 3.5 : b.owner ? 2 : 1.5, opacity: 0.95,
                    fillColor: monoColor(b), fillOpacity: 0.95,
                }).bindTooltip(`${esc(b.address || '')}<br>${b.nb_log} logements · ${esc(b.owner ? `${b.owner.legal_form || ''} ${b.owner.name || ''}` : 'propriétaire non identifié')}${b.signal_level ? `<br>Signal de vente ${b.signal_level}` : ''}`)
                    .on('click', () => setSheet({ id: b.id })).addTo(group);
            }
            return;
        }
        const top = new Set(ranked.slice(0, 5).map(t => t.o.number));
        for (const { o } of [...ranked].reverse()) {
            if (o.lat == null || o.lon == null) continue;
            const on = o.number === selected;
            if (top.has(o.number) || on) {
                const n = rank(o.number);
                L.marker([o.lat, o.lon], {
                    icon: L.divIcon({
                        className: '', iconSize: [60, 60], iconAnchor: [30, 30],
                        html: `<div class="cmd-reticle${on ? ' on' : ''}${n === 1 ? ' first' : ''}"><i style="background:${DPE_COLORS[o.label].bg}"></i><b>#${n}</b></div>`,
                    }),
                    zIndexOffset: on ? 1000 : 500 - n,
                }).on('click', () => focus(o)).bindTooltip(`#${n} · ${esc(shortAddress(o.address))}`, { direction: 'top', offset: [0, -14] }).addTo(group);
            } else {
                L.circleMarker([o.lat, o.lon], { radius: 5.5, color: '#0A0F1A', weight: 1.5, fillColor: DPE_COLORS[o.label].bg, fillOpacity: 0.92 })
                    .on('click', () => focus(o)).bindTooltip(esc(shortAddress(o.address))).addTo(group);
            }
        }
        // Sellers who asked to be called back, from the estimator
        for (const l of newLeads) {
            if (l.lat == null || l.lon == null) continue;
            L.circleMarker([l.lat, l.lon], { radius: 7, color: '#6FBF8E', weight: 2.5, fillColor: '#0A0F1A', fillOpacity: 0.9 })
                .bindTooltip(`Demande d'estimation · ${esc(l.name)}`).addTo(group);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [view, dpe, mono, zoomOk, ranked, selected, leads, focus, mapReady, alertZones, fiche.results, signalsData, signalFilter, salesData, tour]);

    // --- Command bar ---
    const [query, setQuery] = useState('');
    const [places, setPlaces] = useState<{ label: string; lat: number; lon: number; city: string }[]>([]);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [cursor, setCursor] = useState(0);
    const input = useRef<HTMLInputElement>(null);
    useEffect(() => {
        if (query.trim().length < 3) { setPlaces([]); return; }
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            try {
                const res = await fetch(`https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(query)}&limit=4`, { signal: controller.signal });
                const data = await res.json();
                setPlaces((data.features || []).map((f: any) => ({ label: f.properties.label, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0], city: f.properties.city })));
            } catch { /* suggestions are optional */ }
        }, 220);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [query]);
    const commands = useMemo(() => {
        const q = query.trim().toLowerCase();
        const list: { label: string; hint: string; run: () => void }[] = [];
        const hits = ranked.filter(t => q && t.o.address.toLowerCase().includes(q)).slice(0, 4);
        hits.forEach(t => list.push({ label: shortAddress(t.o.address), hint: `Cible #${rank(t.o.number)}`, run: () => focus(t.o) }));
        places.forEach(p => list.push({ label: p.label, hint: 'Scanner ce secteur', run: () => { setCenter({ lat: p.lat, lon: p.lon, label: p.city }); setView('radar'); mapRef.current?.setView([p.lat, p.lon], 14.5); } }));
        const base = [
            { label: 'Radar', hint: 'Vue d\'ensemble', run: backToRadar },
            { label: 'Suivi', hint: 'Relances, rendez-vous, mandats', run: () => setView('suivi') },
            ...(ranked[0] ? [{ label: 'Ouvrir la meilleure cible', hint: shortAddress(ranked[0].o.address), run: () => focus(ranked[0].o) }] : []),
            ...(current ? [{ label: 'Courrier à la cible', hint: shortAddress(current.o.address), run: () => setLetterFor({ address: current.o.address, label: current.o.label, dpeNumber: current.o.number }) }] : []),
            { label: 'Tous les DPE récents', hint: 'Carte, filtres, alerte, export CSV', run: () => showMap('dpe') },
            { label: 'Immeubles entiers', hint: 'Un propriétaire pour tout l\'immeuble', run: () => showMap('immeubles') },
        ];
        base.filter(c => !q || `${c.label} ${c.hint}`.toLowerCase().includes(q)).forEach(c => list.push(c));
        return list.slice(0, 8);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query, places, ranked, current, focus, backToRadar]);
    const runCommand = (i: number) => {
        commands[i]?.run();
        setQuery('');
        setPaletteOpen(false);
        input.current?.blur();
    };

    // --- Keyboard ---
    const dialogOpen = !!(letterFor || ownerFor || dossier);
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.current?.focus(); setPaletteOpen(true); return; }
            const tag = (e.target as HTMLElement)?.tagName;
            if (dialogOpen || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.metaKey || e.ctrlKey || e.altKey) return;
            const list = view === 'radar' ? targets.map(t => t.o) : ranked.map(t => t.o);
            const i = list.findIndex(o => o.number === selected);
            if (e.key === '/') { e.preventDefault(); input.current?.focus(); setPaletteOpen(true); }
            else if (e.key === 'Escape' && view !== 'radar') backToRadar();
            else if (view === 'radar' && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
                e.preventDefault();
                const next = list[Math.max(0, Math.min(list.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))];
                if (next) setSelected(next.number);
            } else if (view === 'radar' && e.key === 'Enter' && i >= 0) focus(list[i]);
            else if (view === 'cible' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft') && list.length) {
                focus(list[(i + (e.key === 'ArrowRight' ? 1 : -1) + list.length) % list.length]);
            } else if (view === 'cible' && current) {
                const o = current.o;
                const k = e.key.toLowerCase();
                if (k === 'c') setLetterFor({ address: o.address, label: o.label, dpeNumber: o.number });
                else if (k === 'p') setOwnerFor({ address: o.address, lat: o.lat, lon: o.lon });
                else if (k === 'd') setDossier({ o, audience: 'proprietaire' });
                else if (k === 'a') setDossier({ o, audience: 'acheteur' });
                else if (k === 's') navigate(`/?dpe=${encodeURIComponent(o.number)}`);
                else if (k === 'f') window.open(streetView(o), '_blank', 'noopener');
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [view, targets, ranked, selected, current, dialogOpen, focus, backToRadar]);

    // --- Gates ---
    if (!session || (me && !pro)) {
        return (
            <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
                <div className="max-w-md text-center">
                    <Lock className="mx-auto text-brass" />
                    <h1 className="mt-4 text-3xl text-ink">Prospection</h1>
                    <p className="mt-3 text-muted">Le cockpit de prospection : le radar de votre secteur, vos cibles classées par score, chaque bien chiffré et toutes les actions à portée de clavier. Inclus dans la formule Pro.</p>
                    <div className="mt-6 flex justify-center gap-3">
                        {!session && <Button onClick={() => openLogin('Connectez-vous pour ouvrir la prospection.')} disabled={!config?.auth_enabled}>Se connecter</Button>}
                        <Button variant={session ? 'primary' : 'secondary'} onClick={() => navigate('/demo#prospection')}>Voir la démo</Button>
                    </div>
                </div>
            </div>
        );
    }

    const hello = `Bonjour${agentName ? ` ${agentName}` : ''}.`;
    const top = ranked[0]?.o;
    const why = (o: Opportunity) => {
        const age = daysSince(o.dpe_date);
        const rental = (o.rental_now || '').toLowerCase();
        const parts = [age < 92 ? `DPE réalisé ${age < 31 ? 'ce mois-ci' : `il y a ${Math.round(age / 30.4)} mois`} : un DPE récent précède souvent une vente ou une mise en location.` : `${dpeAge(o.dpe_date)}.`];
        if (rental.includes('interdite')) parts.push('Le logement ne peut déjà plus être loué en l\'état.');
        else if (rental.includes('jusqu')) parts.push(`${o.rental_now} : le propriétaire devra choisir entre rénover et vendre.`);
        parts.push(o.value_created > 0
            ? `Angle conseillé : ${rental.includes('interdite') ? 'vendre en l\'état avec un dossier acheteur chiffré, ou ' : ''}rénover pour gagner environ ${eur(o.value_created)}, aides déduites.`
            : 'Angle conseillé : vendre en l\'état, avec un dossier acheteur qui chiffre les travaux et les aides.');
        return parts.join(' ');
    };

    return (
        <div className="h-[100dvh] flex flex-col bg-canvas text-ink overflow-hidden">
            <TourHost screen="prospection" />
            {/* Top bar */}
            <header className="h-14 shrink-0 flex items-center gap-3 sm:gap-5 px-3 sm:px-5 border-b border-line bg-gradient-to-b from-[#0D1424] to-canvas">
                <Link to="/" className="font-serif text-[21px] font-semibold tracking-wide">SPREA</Link>
                <span className="hidden md:inline text-xs text-muted">Prospection · <b className="font-medium text-brass-light">{center?.label || '…'}</b> · rayon 1,5 km</span>
                <div className="relative flex-1 max-w-xl mx-auto" data-tour="cmd-search">
                    <div className="h-9 flex items-center gap-2.5 rounded-[10px] border border-line bg-raised/60 px-3 shadow-[inset_0_0_24px_rgba(201,164,92,0.06)] focus-within:border-brass/60">
                        <Search size={15} className="text-muted shrink-0" />
                        <input ref={input} value={query} onChange={e => { setQuery(e.target.value); setCursor(0); setPaletteOpen(true); }}
                            onFocus={() => setPaletteOpen(true)} onBlur={() => setTimeout(() => setPaletteOpen(false), 150)}
                            onKeyDown={e => {
                                if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(commands.length - 1, c + 1)); }
                                else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)); }
                                else if (e.key === 'Enter') { e.preventDefault(); runCommand(cursor); }
                                else if (e.key === 'Escape') { setPaletteOpen(false); input.current?.blur(); }
                            }}
                            placeholder="Adresse, commune ou commande" aria-label="Commande"
                            className="w-full bg-transparent text-sm text-ink placeholder:text-faint outline-none" />
                        <span className="hidden sm:inline"><Kbd>⌘ K</Kbd></span>
                    </div>
                    {paletteOpen && commands.length > 0 && (
                        <ul className="absolute z-[1200] mt-1.5 w-full rounded-xl border border-line bg-panel shadow-2xl shadow-black/60 overflow-hidden" role="listbox">
                            {commands.map((c, i) => (
                                <li key={`${c.label}-${i}`} role="option" aria-selected={i === cursor}
                                    onMouseDown={e => { e.preventDefault(); runCommand(i); }} onMouseEnter={() => setCursor(i)}
                                    className={`flex items-center justify-between gap-3 px-3.5 py-2.5 text-sm cursor-pointer ${i === cursor ? 'bg-raised text-ink' : 'text-ink-soft'}`}>
                                    <span className="truncate">{c.label}</span><span className="shrink-0 text-xs text-faint">{c.hint}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
                <span className="hidden lg:flex items-center gap-2 text-xs text-muted">
                    <span className={`h-[7px] w-[7px] rounded-full ${scanning ? 'bg-brass animate-pulse' : 'bg-sage shadow-[0_0_10px_#6FBF8E]'}`} />
                    {scanning ? 'Analyse en cours' : 'Données ADEME, DVF, BODACC'}
                </span>
            </header>

            <div className="flex-1 min-h-0 flex flex-col-reverse lg:flex-row">
                {/* Rail */}
                <nav className="shrink-0 flex lg:flex-col items-center justify-start sm:justify-around lg:justify-start gap-1 sm:gap-1.5 overflow-x-auto lg:overflow-x-visible lg:overflow-y-auto lg:w-[68px] border-t lg:border-t-0 lg:border-r border-line bg-[#0B1120] py-1.5 lg:pt-3.5" aria-label="Vues">
                    {([
                        ['radar', Radar, 'Radar', () => backToRadar()],
                        ['signaux', Flame, 'Signaux', () => showMap('signaux')],
                        ['dpe', MapPin, 'Récents', () => showMap('dpe')],
                        ['immeubles', Building2, 'Immeubles', () => showMap('immeubles')],
                        ['ventes', Receipt, 'Ventes', () => showMap('ventes')],
                        ['alertes', Bell, 'Alertes', () => showMap('alertes')],
                        ['fiche', FileSearch, 'DPE', () => showMap('fiche')],
                        ['tournee', Route, 'Tournée', () => showMap('tournee')],
                        ['cible', Star, 'Cible', () => { const t = current?.o || ranked[0]?.o; if (t) focus(t); }],
                        ['suivi', Workflow, 'Suivi', () => setView('suivi')],
                    ] as const).map(([v, Icon, label, go]) => (
                        <button key={v} type="button" onClick={go} aria-current={view === v ? 'page' : undefined} data-tour={v === 'suivi' ? 'cmd-suivi' : v === 'dpe' ? 'cmd-layers' : undefined}
                            className={`relative shrink-0 w-[46px] sm:w-12 h-[52px] rounded-xl flex flex-col items-center justify-center gap-0.5 text-[10px] ${view === v ? 'text-brass-light bg-brass/10 lg:shadow-[inset_2px_0_0_#C9A45C]' : 'text-faint hover:text-ink'}`}>
                            <Icon size={19} strokeWidth={1.6} />{label}
                            {v === 'tournee' && tour.length > 0 && <span className="absolute top-1 right-1 h-4 min-w-4 px-1 rounded-full bg-brass text-[9px] text-canvas flex items-center justify-center">{tour.length}</span>}
                            {v === 'suivi' && due.length > 0 && <span className="absolute top-1 right-1 h-4 min-w-4 px-1 rounded-full bg-coral text-[9px] text-white flex items-center justify-center">{due.length}</span>}
                        </button>
                    ))}
                    {([
                        ['/contacts', Users, 'Leads', newLeads.length],
                    ] as const).map(([to, Icon, label, badge]) => (
                        <Link key={to} to={to} className="relative shrink-0 w-[46px] sm:w-12 h-[52px] rounded-xl flex flex-col items-center justify-center gap-0.5 text-[10px] text-faint hover:text-ink">
                            <Icon size={19} strokeWidth={1.6} />{label}
                            {badge > 0 && <span className="absolute top-1 right-1 h-4 min-w-4 px-1 rounded-full bg-coral text-[9px] text-white flex items-center justify-center">{badge}</span>}
                        </Link>
                    ))}
                </nav>

                {/* Main */}
                <section className="relative flex-1 min-h-0 overflow-hidden">
                    <div ref={setMapEl} className={`sprea-map cmd-map absolute inset-0 ${view === 'suivi' ? 'invisible' : ''}`} />
                    {/* Above the map tiles (Leaflet panes: tiles 200, shapes 400, markers 600) */}
                    {view !== 'suivi' && <div className="absolute inset-0 z-[405] pointer-events-none cmd-vignette" />}

                    {view === 'radar' && radar && radar.r > 20 && (
                        <svg className="absolute inset-0 z-[410] pointer-events-none" width="100%" height="100%" aria-hidden>
                            <g transform={`translate(${radar.x} ${radar.y})`}>
                                {[1, 0.66, 0.33].map((k, i) => (
                                    <circle key={k} r={radar.r * k} fill="none" stroke="#C9A45C" strokeOpacity={i ? 0.16 : 0.5} strokeWidth={i ? 1 : 1.6} strokeDasharray={i ? undefined : '6 6'} />
                                ))}
                                <g className="cmd-sweep"><path d={`M0 0 L${radar.r} 0 A${radar.r} ${radar.r} 0 0 0 ${radar.r * Math.cos(-Math.PI / 4)} ${radar.r * Math.sin(-Math.PI / 4)} Z`} fill="url(#cmdsweep)" /></g>
                                <text x={radar.r + 6} y={14} fill="#6C778C" fontSize="9" letterSpacing="1.5">1,5 KM</text>
                                {['N', 'E', 'S', 'O'].map((t, i) => (
                                    <text key={t} transform={`rotate(${i * 90}) translate(0 ${-radar.r - 6})`} fill="#6C778C" fontSize="9" textAnchor="middle" letterSpacing="2">{t}</text>
                                ))}
                            </g>
                            <defs>
                                <linearGradient id="cmdsweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#C9A45C" stopOpacity="0" /><stop offset="1" stopColor="#C9A45C" stopOpacity={scanning ? 0.4 : 0.22} /></linearGradient>
                            </defs>
                        </svg>
                    )}

                    {/* Radar HUD */}
                    {view === 'radar' && (
                        <>
                            <div data-tour="cmd-kpis" className="absolute top-2.5 sm:top-3.5 left-2.5 sm:left-3.5 right-14 sm:right-3.5 z-[500] grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-2 sm:gap-2.5 pointer-events-none">
                                <Kpi label="Nouveaux DPE · 7 j" value={kpis.newDpe} sub="classés E, F ou G" />
                                <Kpi label="Biens à fort potentiel" value={scan ? scan.positive : null} sub={scan ? `sur ${scan.analysed} analysés` : 'analyse en cours'} loading={scanning} />
                                <Kpi label="Valeur à débloquer" value={scan ? (unlocked >= 1e6 ? `${(unlocked / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M€` : `${Math.round(unlocked / 1000)} k€`) : null} sub="par la rénovation" loading={scanning} className="hidden sm:block" />
                                <Kpi label="Signaux de vente SCI" value={kpis.signals} sub={kpis.strongSignals ? `${kpis.strongSignals} fort${kpis.strongSignals > 1 ? 's' : ''}` : 'BODACC'} tone={kpis.signals ? 'coral' : undefined} className="hidden sm:block" />
                                <Kpi label="Demandes vendeurs" value={newLeads.length} sub="via l'estimateur" tone={newLeads.length ? 'sage' : undefined} className="hidden xl:block" />
                            </div>
                            {moved && center && (
                                <button type="button" onClick={() => { const c = mapRef.current!.getCenter(); setCenter({ lat: c.lat, lon: c.lng, label: 'Secteur choisi' }); }}
                                    className="absolute z-[600] top-28 xl:top-24 left-1/2 -translate-x-1/2 h-9 px-4 rounded-full border border-brass/60 bg-panel/90 text-sm text-brass-light shadow-[0_0_24px_rgba(201,164,92,0.25)]">
                                    Scanner ce secteur
                                </button>
                            )}
                            <div className="absolute left-2.5 sm:left-3.5 right-2.5 sm:right-3.5 bottom-2.5 sm:bottom-3.5 z-[500] flex flex-col items-start gap-2.5">
                            <div className="hidden sm:block w-[330px] rounded-xl border border-line bg-[#0D1424]/85 backdrop-blur px-3 py-2.5">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Votre pipeline</p>
                                <div className="mt-1.5 flex gap-1">
                                    {[[toContact.length, 'À contacter'], ...STAGES.map(s => [counts[s.value], s.label.replace(' envoyé', '').replace('Rendez-vous', 'RDV')])].map(([v, l], i) => (
                                        <button key={String(l)} type="button" onClick={() => setView('suivi')} className="flex-1 text-center">
                                            <b className={`block text-base tabular-nums ${i === 4 && Number(v) ? 'text-sage' : 'text-ink'}`}>{v}</b>
                                            <i className="not-italic text-[9.5px] text-faint">{l}</i>
                                            <span className="block h-[3px] rounded bg-brass mx-auto mt-1" style={{ opacity: 1 - i * 0.15, width: `${100 - i * 14}%` }} />
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div data-tour="cmd-briefing" className="self-stretch rounded-2xl border border-brass/30 bg-[#0D1424]/90 backdrop-blur px-3.5 sm:px-4 py-2.5 sm:py-3 flex flex-col md:flex-row md:items-center gap-2 sm:gap-3">
                                <span className="hidden md:block"><Orb /></span>
                                <div className="flex-1 min-w-0">
                                    <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Briefing</p>
                                    <p className="mt-0.5 text-[13px] sm:text-sm text-ink-soft line-clamp-3 md:line-clamp-none">
                                        {error ? <span className="text-coral">{error}</span>
                                            : scanning ? <>{hello} J'analyse les DPE récents de votre secteur : valeur, travaux, aides et loyer pour chaque logement…</>
                                            : scan && top ? <>{hello} {kpis.newDpe != null && <><b className="text-ink">{kpis.newDpe} nouveau{kpis.newDpe > 1 ? 'x' : ''} DPE</b> E, F ou G dans votre zone ces 7 derniers jours. </>}
                                                Priorité : <b className="text-ink">{shortAddress(top.address)}</b>{(top.rental_now || '').toLowerCase().includes('interdite') ? ', location interdite' : ''}{top.value_created > 0 ? <>, <b className="text-brass-light">+{eur(top.value_created)}</b> de valeur à créer</> : ''}.
                                                {due.length > 0 && <> {due.length} relance{due.length > 1 ? 's' : ''} à faire aujourd'hui.</>}
                                                {newLeads.length > 0 && <> {newLeads.length} vendeur{newLeads.length > 1 ? 's' : ''} à rappeler.</>}</>
                                            : <>{hello} Aucun logement chiffrable dans ce rayon : cherchez une autre commune dans la barre du haut.</>}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2 md:max-w-[46%] md:justify-end">
                                    {top && <Chip gold onClick={() => focus(top)}>Ouvrir la cible #1</Chip>}
                                    {due.length > 0 && <Chip className="hidden sm:inline-flex" onClick={() => setView('suivi')}>Voir les {due.length} relance{due.length > 1 ? 's' : ''}</Chip>}
                                    {top && <Chip className="hidden sm:inline-flex" onClick={() => setLetterFor({ address: top.address, label: top.label, dpeNumber: top.number })}>Courrier à la cible #1</Chip>}
                                </div>
                            </div>
                            </div>
                        </>
                    )}

                    {/* Every recent DPE / whole buildings: filters, count, legend */}
                    {(view === 'dpe' || view === 'immeubles') && (
                        <>
                            <div className="absolute top-2.5 sm:top-3.5 left-2.5 sm:left-3.5 right-14 z-[500] flex flex-wrap items-center gap-2">
                                {view === 'dpe' ? (
                                    <>
                                        <div className="flex gap-1.5" role="group" aria-label="Classes DPE">
                                            {LABEL_OPTIONS.map(l => (
                                                <button key={l} type="button" aria-pressed={labels.includes(l)}
                                                    onClick={() => setLabels(prev => (prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l]))}
                                                    className={`h-9 w-9 rounded-lg font-bold border-2 transition-opacity ${labels.includes(l) ? 'opacity-100' : 'opacity-35'}`}
                                                    style={{ backgroundColor: DPE_COLORS[l].bg, color: DPE_COLORS[l].fg, borderColor: labels.includes(l) ? '#E3C98F' : 'transparent' }}>
                                                    {l}
                                                </button>
                                            ))}
                                        </div>
                                        <select value={kind} onChange={e => setKind(e.target.value)} aria-label="Type de bien" className="cmd-select">
                                            {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                                        </select>
                                        <select value={since} onChange={e => setSince(e.target.value)} aria-label="Date du DPE" className="cmd-select">
                                            {SINCE.map(k => <option key={k.value} value={k.value}>DPE · {k.label.toLowerCase()}</option>)}
                                        </select>
                                    </>
                                ) : (
                                    <>
                                        <select value={minLog} onChange={e => setMinLog(e.target.value)} aria-label="Nombre de logements" className="cmd-select">
                                            <option value="3">3 logements ou plus</option>
                                            <option value="5">5 logements ou plus</option>
                                            <option value="10">10 logements ou plus</option>
                                        </select>
                                        <select value={monoDpe} onChange={e => setMonoDpe(e.target.value as 'all' | 'fg')} aria-label="DPE" className="cmd-select">
                                            <option value="all">Tous les DPE</option>
                                            <option value="fg">DPE F ou G (location interdite)</option>
                                        </select>
                                        <select value={monoSignal} onChange={e => setMonoSignal(e.target.value as 'all' | 'any' | 'strong')} aria-label="Signaux de vente" className="cmd-select">
                                            <option value="all">Tous les propriétaires</option>
                                            <option value="any">Avec un signal de vente</option>
                                            <option value="strong">Signal de vente fort</option>
                                        </select>
                                    </>
                                )}
                                <span className="cmd-kpi px-3 py-1.5 text-xs text-ink tabular-nums flex items-center gap-2">
                                    {layerLoading && <Loader2 size={13} className="animate-spin text-brass-light" />}
                                    {!zoomOk ? 'Rapprochez-vous pour afficher la zone'
                                        : view === 'dpe' && dpe ? `${dpe.dwellings.toLocaleString('fr-FR')} logement${dpe.dwellings > 1 ? 's' : ''} · ${dpe.addresses.length.toLocaleString('fr-FR')} adresse${dpe.addresses.length > 1 ? 's' : ''}${dpe.truncated ? ' · zone dense : zoomez' : area?.clamped ? ' · centre de la carte' : ''}`
                                        : view === 'immeubles' && mono ? `${mono.buildings.length.toLocaleString('fr-FR')} immeuble${mono.buildings.length > 1 ? 's' : ''}${mono.truncated ? ' · zone dense : zoomez' : area?.clamped ? ' · centre de la carte' : ''}`
                                        : 'Chargement'}
                                </span>
                            </div>
                            <div className="absolute bottom-2.5 sm:bottom-3.5 left-2.5 sm:left-3.5 z-[500] pointer-events-none">
                            <div className="cmd-kpi px-3 py-1.5 text-xs text-muted flex items-center gap-3">
                                {view === 'immeubles' ? <>
                                    <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: NO_DPE_COLOR }} />sans DPE</span>
                                    <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-[#FF6B4A]" />signal de vente</span>
                                    <span className="text-faint">· couleur : DPE</span>
                                </> : <>
                                    {LABEL_OPTIONS.filter(l => labels.includes(l)).map(l => (
                                        <span key={l} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: DPE_COLORS[l].bg }} />{l}</span>
                                    ))}
                                    <span className="hidden sm:inline text-faint">· taille : nombre de logements</span>
                                </>}
                            </div>
                            </div>
                        </>
                    )}

                    {(view === 'signaux' || view === 'ventes') && (
                        <div className="absolute top-2.5 sm:top-3.5 left-2.5 sm:left-3.5 right-14 z-[500] flex flex-wrap items-center gap-2 pointer-events-none">
                            <span className="cmd-kpi px-3 py-1.5 text-xs text-ink tabular-nums flex items-center gap-2">
                                {toolLoading && <Loader2 size={13} className="animate-spin text-brass-light" />}
                                {!zoomOk ? 'Rapprochez-vous pour afficher la zone'
                                    : view === 'signaux' ? (signalsData ? `${signalsData.total} adresses · ${signalsData.strong} signaux forts` : 'Analyse des adresses (10 à 30 s)')
                                    : salesData ? `${salesData.sales.length} ventes en ${salesMonths} mois` : 'Chargement des ventes'}
                            </span>
                            {view === 'signaux' && (
                                <span className="cmd-kpi px-3 py-1.5 text-xs text-muted flex items-center gap-3">
                                    {(['fort', 'moyen', 'faible'] as const).map(l => (
                                        <span key={l} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: SIGNAL_COLORS[l] }} />{l}</span>
                                    ))}
                                </span>
                            )}
                        </div>
                    )}
                    {view === 'alertes' && (
                        <div className="absolute top-2.5 sm:top-3.5 left-2.5 sm:left-3.5 right-14 z-[500] flex flex-wrap items-center gap-2">
                            <button type="button" onClick={createAlert} disabled={!mapReady}
                                className="cmd-kpi h-9 px-3 text-xs text-brass-light hover:text-ink flex items-center gap-1.5">
                                <Bell size={14} />Créer une alerte ici
                            </button>
                            <span className="cmd-kpi px-3 py-1.5 text-xs text-muted max-w-md">
                                {alertMessage || `Zone visible, classes ${labels.length ? labels.join(', ') : 'E, F, G'} : chaque matin, les nouveaux DPE publiés.`}
                            </span>
                        </div>
                    )}

                    {/* Target HUD */}
                    {view === 'cible' && current && (
                        <>
                            <Callouts o={current.o} w={size.w} h={size.h} />
                            <div className="absolute top-3.5 left-3.5 right-3.5 z-[500] flex flex-wrap items-center justify-between gap-2">
                                <div className="cmd-kpi px-3.5 py-2"><p className="text-[10px] tracking-[0.14em] uppercase text-faint">Cible verrouillée</p><b className="text-base">#{rank(current.o.number)} · {shortAddress(current.o.address)}</b></div>
                                <div className="flex gap-2">
                                    <Chip onClick={() => { const i = ranked.findIndex(t => t.o.number === current.o.number); focus(ranked[(i - 1 + ranked.length) % ranked.length].o); }}><ArrowLeft size={13} />Précédente</Chip>
                                    <Chip onClick={() => { const i = ranked.findIndex(t => t.o.number === current.o.number); focus(ranked[(i + 1) % ranked.length].o); }}>Suivante<ArrowRight size={13} /></Chip>
                                    <Chip onClick={backToRadar}><Kbd>Échap</Kbd>Radar</Chip>
                                </div>
                            </div>
                            <div className="absolute left-2.5 sm:left-3.5 right-2.5 sm:right-3.5 bottom-2.5 sm:bottom-3.5 z-[500] rounded-2xl border border-brass/30 bg-[#0D1424]/90 backdrop-blur px-3.5 sm:px-4 py-2.5 sm:py-3 flex items-center gap-3">
                                <span className="hidden md:block"><Orb /></span>
                                <div><p className="text-[10px] tracking-[0.16em] uppercase text-faint">Pourquoi maintenant</p><p className="mt-0.5 text-[13px] sm:text-sm text-ink-soft line-clamp-3 md:line-clamp-none">{why(current.o)}</p></div>
                            </div>
                        </>
                    )}

                    {/* Follow-up board */}
                    {view === 'suivi' && (
                        <div className="absolute inset-0 overflow-auto p-4 sm:p-5 bg-[radial-gradient(ellipse_at_30%_0%,rgba(201,164,92,0.06),transparent_60%)]">
                            <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Suivi des cibles</p>
                            <h2 className="text-2xl text-ink">{pipeline.filter(p => p.status !== 'ecarte').length} bien{pipeline.length > 1 ? 's' : ''} en cours, {counts.mandat} mandat{counts.mandat > 1 ? 's' : ''}</h2>
                            <div className="mt-4 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 min-h-[60%]">
                                <Column title="À contacter" count={toContact.length}>
                                    {toContact.slice(0, 6).map(t => (
                                        <BoardCard key={t.o.number} label={t.o.label} title={shortAddress(t.o.address)} sub={`Score ${t.score}${t.o.value_created > 0 ? ` · +${eur(t.o.value_created)}` : ''}`} onClick={() => focus(t.o)} />
                                    ))}
                                </Column>
                                {STAGES.map(s => {
                                    const items = pipeline.filter(p => p.status === s.value);
                                    return (
                                        <Column key={s.value} title={s.label} count={items.length}>
                                            {items.slice(0, 8).map(p => {
                                                const t = ranked.find(r => r.o.number === p.number);
                                                const late = (p.status === 'courrier' || p.status === 'relance') && daysSince(p.updated_at) >= REMIND_DAYS;
                                                return <BoardCard key={p.number} label={t?.o.label} title={shortAddress(p.address || p.number)}
                                                    sub={late ? 'Relance due' : `Depuis le ${p.updated_at ? new Date(p.updated_at).toLocaleDateString('fr-FR') : '–'}${p.mine ? '' : ' · un collègue'}`}
                                                    late={late} onClick={() => (t ? focus(t.o) : navigate(`/?dpe=${encodeURIComponent(p.number)}`))} />;
                                            })}
                                        </Column>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {scanning && view === 'radar' && (
                        <div className="absolute z-[550] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 rounded-full border border-brass/40 bg-panel/90 px-4 h-10 text-sm text-brass-light">
                            <Loader2 size={15} className="animate-spin" />Scan du secteur : jusqu'à 150 DPE, 10 à 40 s
                        </div>
                    )}
                </section>

                {/* Side panel */}
                <aside className="lg:w-[392px] shrink-0 max-h-[38vh] lg:max-h-none border-b lg:border-b-0 lg:border-l border-line bg-panel flex flex-col min-h-0">
                    {view === 'radar' && (
                        <>
                            <div data-tour="cmd-targets" className="px-[18px] pt-4 pb-3 border-b border-line">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Cibles prioritaires</p>
                                <h2 className="text-[19px] text-ink">{scan ? `${targets.length} bien${targets.length > 1 ? 's' : ''}, ${{ score: 'triés par score', fresh: 'les plus récents d\'abord', value: 'par valeur créée', todo: 'pas encore contactés' }[sortBy]}` : 'Analyse du secteur…'}</h2>
                                <div className="mt-2.5 flex flex-wrap gap-1.5">
                                    {([['score', 'Score'], ['fresh', 'Fraîcheur'], ['value', 'Valeur'], ['todo', 'Non contactés']] as const).map(([k, l]) => (
                                        <Chip key={k} gold={sortBy === k} onClick={() => setSortBy(k)}>{l}</Chip>
                                    ))}
                                </div>
                            </div>
                            <ol className="flex-1 overflow-y-auto">
                                {!scan && Array.from({ length: 6 }).map((_, i) => <li key={i} className="h-[86px] mx-[18px] my-2 rounded-xl bg-raised/60 animate-pulse" />)}
                                {targets.map(({ o, score: s }) => (
                                    <TargetRow key={o.number} o={o} score={s} on={o.number === selected} status={statuses[o.number]}
                                        onHover={() => setSelected(o.number)} onOpen={() => focus(o)} />
                                ))}
                            </ol>
                            <p className="hidden lg:flex px-[18px] py-3 border-t border-line text-[11.5px] text-faint justify-between gap-3">
                                <span><Kbd>↑</Kbd> <Kbd>↓</Kbd> naviguer · <Kbd>↵</Kbd> ouvrir</span>
                                <span title="Valeur créée par la rénovation (40), fraîcheur du DPE (35), urgence locative (25)">Score : valeur × fraîcheur × urgence</span>
                            </p>
                        </>
                    )}
                    {view === 'signaux' && (
                        <SignalsPanel data={signalsData} loading={toolLoading} zoomOk={zoomOk} filter={signalFilter} onFilter={setSignalFilter}
                            onFocus={it => mapRef.current?.flyTo([it.lat, it.lon], 18, { duration: 0.6 })} inTour={inTour}
                            onTour={it => addStop({ key: `${it.lat},${it.lon}`, address: it.address, lat: it.lat, lon: it.lon, label: it.label, dpeNumber: it.dpe_number })}
                            onLetter={it => setLetterFor({ address: it.address, label: it.label as DPEClass, dpeNumber: it.dpe_number! })}
                            onOwner={it => setOwnerFor({ address: it.address, lat: it.lat, lon: it.lon })} />
                    )}
                    {view === 'ventes' && (
                        <SalesPanel data={salesData} loading={toolLoading} zoomOk={zoomOk} months={salesMonths} onMonths={setSalesMonths}
                            onFocus={sl => mapRef.current?.flyTo([sl.lat, sl.lon], 18, { duration: 0.6 })} onNeighbours={setNeighbourFor} />
                    )}
                    {view === 'tournee' && (
                        <TourPanel stops={tour} onChange={setTour} onFocus={st => mapRef.current?.flyTo([st.lat, st.lon], 18, { duration: 0.6 })}
                            onDelivered={delivered} />
                    )}
                    {view === 'alertes' && (
                        <div className="flex-1 overflow-y-auto">
                            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Alertes nouveaux DPE</p>
                                <h2 className="text-[19px] text-ink">Chaque matin, les DPE publiés dans vos zones</h2>
                                <p className="mt-1 text-xs text-faint">Un nouveau DPE précède souvent une vente ou une mise en location.</p>
                            </div>
                            <AlertsPanel compact reload={alertsReload} onZones={setAlertZones}
                                onZone={z => mapRef.current?.flyTo([z.lat, z.lon], z.radius_m > 1500 ? 14 : 15, { duration: 0.8 })} />
                        </div>
                    )}
                    {view === 'fiche' && (
                        <div className="flex-1 overflow-y-auto">
                            <div className="px-[18px] pt-4 pb-4 border-b border-line">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Fiche DPE</p>
                                <h2 className="text-[19px] text-ink">Un bien précis</h2>
                                <p className="mt-1 text-xs text-faint">Adresse ou numéro de DPE (13 caractères, en haut du diagnostic).</p>
                                <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); searchFiche(String(new FormData(e.currentTarget).get('q') || '')); }}>
                                    <input name="q" aria-label="Adresse ou numéro de DPE" placeholder="12 rue Nationale, Lille ou 2659E…"
                                        className="flex-1 min-w-0 h-10 rounded-[10px] border border-line bg-raised px-3 text-sm text-ink placeholder:text-faint" />
                                    <Button type="submit" className="h-10 px-3" disabled={fiche.loading}>
                                        {fiche.loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
                                    </Button>
                                </form>
                                {fiche.error && <p role="alert" className="mt-2 text-xs text-coral">{fiche.error}</p>}
                            </div>
                            <ul className="divide-y divide-line/70">
                                {fiche.results.map(r => (
                                    <li key={r.ademe_dpe_number || r.address} className="px-[18px] py-3">
                                        <button type="button" className="flex items-start gap-3 text-left w-full"
                                            onClick={() => r.latitude != null && r.longitude != null && mapRef.current?.flyTo([r.latitude, r.longitude], 18, { duration: 0.6 })}>
                                            <DpeBadge label={r.label as DPEClass} size="sm" />
                                            <span className="min-w-0">
                                                <span className="block text-sm text-ink">{r.address}</span>
                                                <span className="block text-xs text-faint">
                                                    {[r.buildingType, r.surface ? `${Math.round(r.surface)} m²` : null, r.details,
                                                      r.dpeDate ? `DPE du ${formatDate(r.dpeDate)}` : null].filter(Boolean).join(' · ')}
                                                </span>
                                            </span>
                                        </button>
                                        <div className="mt-2 ml-10 flex flex-wrap gap-x-3 gap-y-1.5 text-xs">
                                            {r.ademe_dpe_number && (
                                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1"
                                                    onClick={() => navigate(`/?dpe=${encodeURIComponent(r.ademe_dpe_number!)}`)}>
                                                    <Calculator size={12} />Dossier de rénovation
                                                </button>
                                            )}
                                            {r.ademe_dpe_number && r.label && (
                                                <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                    onClick={() => setLetterFor({ address: r.address, label: r.label as DPEClass, dpeNumber: r.ademe_dpe_number! })}>
                                                    <QrCode size={12} />Courrier
                                                </button>
                                            )}
                                            {r.latitude != null && r.longitude != null && (
                                                <button type="button" className="text-muted hover:text-ink disabled:text-faint flex items-center gap-1" disabled={inTour(`${r.latitude},${r.longitude}`)}
                                                    onClick={() => addStop({ key: `${r.latitude},${r.longitude}`, address: r.address, lat: r.latitude!, lon: r.longitude!,
                                                        label: (r.label || null) as DPEClass | null, dpeNumber: r.ademe_dpe_number || null })}>
                                                    <Route size={12} />{inTour(`${r.latitude},${r.longitude}`) ? 'Dans la tournée' : 'Tournée'}
                                                </button>
                                            )}
                                            {r.latitude != null && r.longitude != null && (
                                                <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                    onClick={() => setOwnerFor({ address: r.address, lat: r.latitude!, lon: r.longitude! })}>
                                                    <UserSearch size={12} />Connaître le propriétaire
                                                </button>
                                            )}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                            {!fiche.results.length && !fiche.loading && (
                                <p className="px-[18px] py-4 text-xs text-faint">
                                    Le dossier de rénovation chiffre les travaux, les aides et la valeur après travaux : de quoi préparer un rendez-vous
                                    ou appuyer la vente d'une passoire auprès des acquéreurs.
                                </p>
                            )}
                        </div>
                    )}
                    {view === 'dpe' && (
                        <>
                            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">DPE récents de la carte</p>
                                <div className="flex items-center justify-between gap-2">
                                    <h2 className="text-[19px] text-ink">{!zoomOk ? 'Zoomez sur un quartier' : dpe?.locked ? 'Réservé aux abonnés' : dpe ? `${dpeList.length.toLocaleString('fr-FR')} adresse${dpeList.length > 1 ? 's' : ''}` : 'Chargement…'}</h2>
                                    <Button variant="secondary" className="h-8 px-2.5 text-xs" onClick={exportCsv} disabled={!dpeList.length}><Download size={13} />CSV</Button>
                                </div>
                                {zoomOk && dpe && !dpe.locked && (
                                    <>
                                        <button type="button" onClick={createAlert} className="mt-2.5 flex items-center gap-1.5 text-xs text-brass-light hover:text-ink">
                                            <Bell size={13} />Créer une alerte sur cette zone
                                        </button>
                                        {alertMessage && <p className="mt-1.5 text-xs text-faint">{alertMessage} <button type="button" onClick={() => showMap('alertes')} className="underline text-brass-light">Voir les alertes</button></p>}
                                    </>
                                )}
                            </div>
                            <ul className="flex-1 overflow-y-auto divide-y divide-line/70">
                                {dpeList.slice(0, 300).map(a => (
                                    <li key={`${a.address || ''}@${a.lat},${a.lon}`} className="px-[18px] py-3">
                                        <button type="button" onClick={() => focusAddress(a)} className="flex items-start gap-3 text-left w-full">
                                            <DpeBadge label={a.worst} size="sm" />
                                            <span className="min-w-0">
                                                <span className="block text-sm text-ink truncate">{a.address}</span>
                                                <span className="block text-xs text-faint">
                                                    {a.dpe!.length} logement{a.dpe!.length > 1 ? 's' : ''} · {a.dpe![0].kind || 'Logement'}
                                                    {a.dpe![0].surface ? ` · ${Math.round(a.dpe![0].surface)} m²` : ''} · DPE du {formatDate(latestDate(a))}
                                                </span>
                                            </span>
                                        </button>
                                        <div className="mt-2 ml-10 flex flex-wrap gap-x-3 gap-y-1.5 text-xs">
                                            {isBuilding(a.dpe![0]) ? (
                                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1"
                                                    onClick={() => setSheet({ near: { lat: a.lat, lon: a.lon, address: a.address || '' } })}>
                                                    <Building2 size={12} />Fiche immeuble
                                                </button>
                                            ) : (
                                                <button type="button" className="text-brass-light hover:text-ink flex items-center gap-1"
                                                    onClick={() => navigate(`/?dpe=${encodeURIComponent(a.dpe![0].number)}`)}>
                                                    <Calculator size={12} />Simuler la rénovation
                                                </button>
                                            )}
                                            <button type="button" className="text-muted hover:text-ink disabled:text-faint flex items-center gap-1" disabled={inTour(`${a.lat},${a.lon}`)}
                                                onClick={() => addStop({ key: `${a.lat},${a.lon}`, address: a.address || '', lat: a.lat, lon: a.lon, label: a.worst, dpeNumber: a.dpe![0].number })}>
                                                <Route size={12} />{inTour(`${a.lat},${a.lon}`) ? 'Dans la tournée' : 'Tournée'}
                                            </button>
                                            <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                onClick={() => setLetterFor({ address: a.address || '', label: a.worst, dpeNumber: a.dpe![0].number })}>
                                                <QrCode size={12} />Courrier
                                            </button>
                                            <button type="button" className="text-muted hover:text-ink flex items-center gap-1"
                                                onClick={() => setOwnerFor({ address: a.address || '', lat: a.lat, lon: a.lon })}>
                                                <UserSearch size={12} />Connaître le propriétaire
                                            </button>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                            {dpeList.length > 300 && <p className="px-[18px] py-2 text-xs text-faint border-t border-line">300 premières adresses affichées : l'export CSV contient tout.</p>}
                        </>
                    )}
                    {view === 'immeubles' && (
                        <>
                            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Immeubles entiers</p>
                                <h2 className="text-[19px] text-ink">{!zoomOk ? 'Zoomez sur un quartier' : mono ? `${mono.buildings.length.toLocaleString('fr-FR')} immeuble${mono.buildings.length > 1 ? 's' : ''} détenu${mono.buildings.length > 1 ? 's' : ''} par une société` : 'Chargement…'}</h2>
                                <p className="mt-1 text-xs text-faint">Un seul propriétaire pour tout l'immeuble : un interlocuteur, plusieurs lots.</p>
                            </div>
                            <div className="flex-1 overflow-y-auto">
                                {mono && <MonoproList buildings={mono.buildings}
                                    onFocus={b => mapRef.current?.setView([b.lat, b.lon], Math.max(mapRef.current.getZoom(), 17))}
                                    onOpen={b => setSheet({ id: b.id })} />}
                            </div>
                        </>
                    )}
                    {view === 'cible' && current && (
                        <TargetSheet o={current.o} score={current.score} status={statuses[current.o.number]} item={pipeline.find(p => p.number === current.o.number)}
                            onLetter={() => setLetterFor({ address: current.o.address, label: current.o.label, dpeNumber: current.o.number })}
                            onOwner={() => setOwnerFor({ address: current.o.address, lat: current.o.lat, lon: current.o.lon })}
                            onDossier={a => setDossier({ o: current.o, audience: a })}
                            onStatus={s => setStatus(current.o, s)} />
                    )}
                    {view === 'cible' && !current && (
                        <p className="p-6 text-sm text-muted">{scanning ? 'Analyse en cours…' : 'Choisissez une cible sur le radar.'}</p>
                    )}
                    {view === 'suivi' && (
                        <Today due={due} leads={newLeads} rdv={pipeline.filter(p => p.status === 'rendez_vous')} toContact={toContact.length} won={won} goal={goal}
                            onGoal={g => { setGoal(g); try { localStorage.setItem(GOAL_KEY, String(g)); } catch { /* private mode */ } }}
                            onOpen={n => { const t = ranked.find(r => r.o.number === n); if (t) focus(t.o); else navigate(`/?dpe=${encodeURIComponent(n)}`); }}
                            onFirst={() => toContact[0] && focus(toContact[0].o)} />
                    )}
                </aside>
            </div>

            {letterFor && <LetterDialog target={letterFor} onClose={() => setLetterFor(null)} />}
            {neighbourFor && <NeighbourLetterDialog sale={neighbourFor} onClose={() => setNeighbourFor(null)} />}
            {sheet && <MonoproSheet target={sheet} onClose={() => setSheet(null)}
                onFocus={(lat, lon) => mapRef.current?.setView([lat, lon], Math.max(mapRef.current.getZoom(), 17))} />}
            {ownerFor && <OwnerRequestDialog target={ownerFor} onClose={() => setOwnerFor(null)} />}
            {dossier && <DossierDialog audience={dossier.audience} preview={dossier.o}
                request={{ url: '/api/opportunities/dossier', body: { number: dossier.o.number } }} onClose={() => setDossier(null)} />}
        </div>
    );
}

const streetView = (o: Opportunity) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${o.lat},${o.lon}`;

function Kpi({ label, value, sub, tone, loading, className = '' }: { label: string; value: number | string | null; sub: string; tone?: 'coral' | 'sage'; loading?: boolean; className?: string }) {
    const color = tone === 'coral' ? 'text-[#F2A08C]' : tone === 'sage' ? 'text-sage' : 'text-ink';
    return (
        <div className={`cmd-kpi px-3 py-2.5 ${className}`}>
            <p className="text-[10px] tracking-[0.14em] uppercase text-faint truncate">{label}</p>
            <b className={`block mt-0.5 text-[22px] font-semibold tabular-nums ${color}`}>{value ?? (loading ? <Loader2 size={18} className="animate-spin text-faint my-1.5" /> : '–')}</b>
            <span className={`text-[11px] ${tone ? color : 'text-sage'}`}>{sub}</span>
        </div>
    );
}

function Chip({ children, gold, onClick, className = '' }: { children: React.ReactNode; gold?: boolean; onClick?: () => void; className?: string }) {
    return (
        <button type="button" onClick={onClick}
            className={`h-7 inline-flex items-center gap-1.5 rounded-full border px-2.5 text-xs whitespace-nowrap transition-colors ${className} ${gold ? 'border-brass/60 text-brass-light bg-brass/10' : 'border-line text-ink-soft bg-raised hover:border-brass/40'}`}>
            {children}
        </button>
    );
}

function TargetRow({ o, score, on, status, onHover, onOpen }: { o: Opportunity; score: number; on: boolean; status?: FollowUp; onHover: () => void; onOpen: () => void }) {
    const ref = useRef<HTMLLIElement>(null);
    // Only the list scrolls (scrollIntoView would also move the fixed-height page)
    useEffect(() => {
        const el = ref.current, list = el?.parentElement;
        if (!on || !el || !list) return;
        const top = el.offsetTop - list.offsetTop;
        if (top < list.scrollTop) list.scrollTop = top;
        else if (top + el.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + el.offsetHeight - list.clientHeight;
    }, [on]);
    return (
        <li ref={ref}>
            <button type="button" onClick={onOpen} onMouseEnter={onHover}
                className={`w-full text-left flex items-center gap-3 px-[18px] py-3 border-b border-line/70 transition-colors ${on ? 'bg-gradient-to-r from-brass/10 to-transparent shadow-[inset_2px_0_0_#C9A45C]' : 'hover:bg-raised/40'}`}>
                <Ring value={score} />
                <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-2"><Badge label={o.label} /><b className="font-medium truncate">{shortAddress(o.address)}</b></span>
                    <span className="block mt-0.5 text-[11.5px] text-faint">{o.kind} · {Math.round(o.surface)} m²{o.period ? ` · ${o.period}` : ''}</span>
                    <span className="mt-1.5 flex flex-wrap gap-1">{tags(o, status).map(t => <span key={t.text} className={`text-[10.5px] rounded-[5px] px-1.5 ${TONES[t.tone]}`}>{t.text}</span>)}</span>
                </span>
                <span className="text-right shrink-0"><b className="block tabular-nums">{eur(o.price)}</b>{o.value_created > 0 && <span className="text-[11.5px] text-sage tabular-nums">+{eur(o.value_created)}</span>}</span>
            </button>
        </li>
    );
}

// Four figures around the locked target, joined to it (the map is centered on it)
function Callouts({ o, w, h }: { o: Opportunity; w: number; h: number }) {
    if (w < 640 || h < 420) return null;
    const cx = w / 2, cy = h / 2;
    const boxes = [
        { x: cx - 360, y: cy - 190, label: 'Valeur aujourd\'hui', value: `≈ ${eur(o.price)}`, sub: 'ventes DVF comparables', anchor: 'right' },
        { x: cx + 170, y: cy - 190, label: 'Travaux', value: eurRange(o.works_low, o.works_high), sub: o.works_names.slice(0, 3).join(', ').toLowerCase(), anchor: 'left' },
        { x: cx - 360, y: cy + 110, label: 'Aides estimées', value: o.aids ? `− ${eur(o.aids)}` : '–', sub: 'MaPrimeRénov\', CEE', anchor: 'right', tone: 'text-sage' },
        { x: cx + 170, y: cy + 110, label: `Après travaux · DPE ${o.new_label}`, value: `≈ ${eur(o.resale)}`, sub: o.value_created > 0 ? `+${eur(o.value_created)} créés` : 'valeur après rénovation', anchor: 'left', subTone: 'text-sage' },
    ];
    return (
        <div className="absolute inset-0 z-[450] pointer-events-none">
            <svg width={w} height={h} className="absolute inset-0">
                <g stroke="#C9A45C" strokeOpacity=".7" fill="none">
                    {boxes.map(b => {
                        const ex = b.anchor === 'right' ? b.x + 190 : b.x;
                        const ey = b.y + 30;
                        return <path key={b.label} d={`M${cx} ${cy} L${ex + (b.anchor === 'right' ? 30 : -30)} ${ey} H${ex}`} />;
                    })}
                </g>
                <circle cx={cx} cy={cy} r={64} fill="none" stroke="#E3C98F" strokeWidth="1.5" strokeDasharray="4 4" className="cmd-spin-slow" style={{ transformOrigin: `${cx}px ${cy}px` }} />
                <circle cx={cx} cy={cy} r={120} fill="none" stroke="#C9A45C" strokeOpacity=".22" />
                <path d={`M${cx - 90} ${cy}h40M${cx + 50} ${cy}h40M${cx} ${cy - 90}v40M${cx} ${cy + 50}v40`} stroke="#E3C98F" strokeWidth="1.6" />
            </svg>
            {boxes.map(b => (
                <div key={b.label} className="absolute w-[190px] rounded-[10px] border border-brass/45 bg-[#0D1424]/90 px-3 py-2" style={{ left: b.x, top: b.y }}>
                    <p className="text-[9.5px] tracking-[0.14em] uppercase text-faint truncate">{b.label}</p>
                    <b className={`block text-base whitespace-nowrap tabular-nums ${b.tone || 'text-ink'}`}>{b.value}</b>
                    <p className={`text-[11px] truncate ${b.subTone || 'text-muted'}`}>{b.sub}</p>
                </div>
            ))}
        </div>
    );
}

function TargetSheet({ o, score: s, status, item, onLetter, onOwner, onDossier, onStatus }: {
    o: Opportunity; score: number; status?: FollowUp; item?: PipelineItem;
    onLetter: () => void; onOwner: () => void; onDossier: (a: Audience) => void; onStatus: (s: FollowUp | '') => void;
}) {
    const action = 'flex items-center gap-2.5 rounded-[10px] border border-line bg-raised px-3 py-2.5 text-[13px] text-ink hover:border-brass/50 text-left';
    const icon = 'shrink-0 text-brass-light';
    const history = [
        item?.updated_at ? [new Date(item.updated_at).toLocaleDateString('fr-FR'), `${FOLLOW_UPS.find(f => f.value === item.status)?.label}${item.mine ? '' : ' (un collègue)'}`] : null,
        o.dpe_date ? [new Date(o.dpe_date).toLocaleDateString('fr-FR'), `Nouveau DPE ${o.label} (ADEME)`] : null,
    ].filter(Boolean) as string[][];
    return (
        <div className="flex-1 overflow-y-auto">
            <div className="px-[18px] pt-4 pb-3.5 border-b border-line">
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Fiche cible</p>
                <h2 className="text-[19px] text-ink">{o.address}</h2>
                <div className="mt-2.5 flex items-center gap-3">
                    <Ring value={s} />
                    <div className="min-w-0">
                        <div className="flex items-center gap-1.5 text-xs text-muted"><Badge label={o.label} />→<Badge label={o.new_label} /><span className="truncate">{o.kind} · {Math.round(o.surface)} m²{o.period ? ` · ${o.period}` : ''}</span></div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                            {tags(o).map(t => <span key={t.text} className={`text-[10.5px] rounded-[5px] px-1.5 ${TONES[t.tone]}`}>{t.text}</span>)}
                            {!!o.rent_month && <span className="text-[10.5px] rounded-[5px] px-1.5 text-sage bg-sage/10">Loyer ≈ {eur(o.rent_month)}/mois</span>}
                        </div>
                    </div>
                </div>
            </div>
            <div className="px-[18px] pb-5">
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-4 mb-2">Contacter</p>
                <div className="grid gap-2">
                    <button type="button" className={`${action} border-brass/60 bg-gradient-to-b from-brass/15 to-brass/5`} onClick={onLetter}><QrCode size={16} className={icon} />Courrier avec QR code<span className="ml-auto"><Kbd>C</Kbd></span></button>
                    <button type="button" className={action} onClick={onOwner}><UserSearch size={16} className={icon} />Connaître le propriétaire<span className="ml-auto"><Kbd>P</Kbd></span></button>
                </div>
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-4 mb-2">Convaincre et vendre</p>
                <div className="grid grid-cols-2 gap-2">
                    <button type="button" className={action} onClick={() => onDossier('proprietaire')}><FileText size={16} className={icon} />Dossier propriétaire<span className="ml-auto"><Kbd>D</Kbd></span></button>
                    <button type="button" className={action} onClick={() => onDossier('acheteur')}><FileText size={16} className={icon} />Dossier acheteur<span className="ml-auto"><Kbd>A</Kbd></span></button>
                    <button type="button" className={action} onClick={() => navigate(`/?dpe=${encodeURIComponent(o.number)}`)}><Calculator size={16} className={icon} />Simuler<span className="ml-auto"><Kbd>S</Kbd></span></button>
                    <a className={action} href={streetView(o)} target="_blank" rel="noopener noreferrer"><Eye size={16} className={icon} />Façade<span className="ml-auto"><Kbd>F</Kbd></span></a>
                </div>
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-4 mb-2">Suivi</p>
                <div className="flex gap-1">
                    {[{ value: '' as const, label: 'À contacter' }, ...STAGES.map(st => ({ value: st.value, label: st.label.replace(' envoyé', '').replace('Rendez-vous', 'RDV') }))].map(st => (
                        <button key={st.value} type="button" onClick={() => onStatus(st.value)} aria-pressed={(status || '') === st.value}
                            className={`flex-1 h-8 rounded-full border text-[11px] ${(status || '') === st.value ? 'border-brass/60 text-brass-light bg-brass/10' : 'border-line text-ink-soft bg-raised hover:border-brass/40'}`}>
                            {st.label}
                        </button>
                    ))}
                </div>
                {!!o.risks?.length && (
                    <>
                        <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-4 mb-2">À vérifier</p>
                        <ul className="text-xs text-muted list-disc pl-4 space-y-0.5">{o.risks.map(r => <li key={r}>{r}</li>)}</ul>
                    </>
                )}
                {history.length > 0 && (
                    <>
                        <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-4 mb-2">Historique</p>
                        <div className="border-l border-line ml-1.5 pl-3 grid gap-2 text-xs text-muted">
                            {history.map(([d, t]) => <p key={t}><b className="font-medium text-ink">{d}</b> · {t}</p>)}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

function Column({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
    return (
        <div className="rounded-2xl border border-line bg-panel p-3 flex flex-col gap-2 min-h-[220px]">
            <div className="flex items-center justify-between"><b className="font-medium text-sm">{title}</b><span className="rounded-full border border-line bg-raised px-2 text-xs text-muted tabular-nums">{count}</span></div>
            {children}
            {count === 0 && <p className="text-xs text-faint mt-1">Aucun bien pour l'instant.</p>}
        </div>
    );
}

function BoardCard({ label, title, sub, late, onClick }: { label?: DPEClass; title: string; sub: string; late?: boolean; onClick: () => void }) {
    return (
        <button type="button" onClick={onClick} className="text-left rounded-[10px] border border-line bg-raised px-2.5 py-2 hover:border-brass/50">
            <span className="flex items-center gap-2">{label && <Badge label={label} />}<b className="font-medium text-[12.5px] truncate">{title}</b></span>
            <span className={`block mt-1 text-[11px] ${late ? 'text-[#F2A08C]' : 'text-faint'}`}>{sub}</span>
        </button>
    );
}

function Today({ due, leads, rdv, toContact, won, goal, onGoal, onOpen, onFirst }: {
    due: PipelineItem[]; leads: EstimateLead[]; rdv: PipelineItem[]; toContact: number; won: number; goal: number;
    onGoal: (g: number) => void; onOpen: (n: string) => void; onFirst: () => void;
}) {
    const actions: { icon: typeof Bell; title: string; sub: string; run: () => void }[] = [
        ...due.map(p => ({ icon: Bell, title: `Relancer ${shortAddress(p.address || p.number)}`, sub: `Sans nouvelle depuis le ${p.updated_at ? new Date(p.updated_at).toLocaleDateString('fr-FR') : '–'}`, run: () => onOpen(p.number) })),
        ...leads.map(l => ({ icon: Users, title: `Rappeler ${l.name}`, sub: `${PROJECTS[l.project] || l.project} · ${shortAddress(l.address)}`, run: () => navigate('/contacts') })),
        ...rdv.map(p => ({ icon: FileText, title: 'Préparer le rendez-vous', sub: shortAddress(p.address || p.number), run: () => onOpen(p.number) })),
        ...(toContact ? [{ icon: QrCode, title: `Écrire aux ${Math.min(toContact, 3)} meilleures cibles`, sub: `${toContact} bien${toContact > 1 ? 's' : ''} pas encore contacté${toContact > 1 ? 's' : ''}`, run: onFirst }] : []),
    ];
    const c = 2 * Math.PI * 36;
    return (
        <div className="flex-1 overflow-y-auto">
            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Aujourd'hui</p>
                <h2 className="text-[19px] text-ink">{actions.length} action{actions.length > 1 ? 's' : ''}</h2>
            </div>
            <div className="p-[18px] grid gap-2">
                {actions.slice(0, 8).map((a, i) => (
                    <button key={`${a.title}-${i}`} type="button" onClick={a.run}
                        className={`flex items-start gap-2.5 rounded-[10px] border px-3 py-2.5 text-left ${i === 0 ? 'border-brass/60 bg-gradient-to-b from-brass/15 to-brass/5' : 'border-line bg-raised hover:border-brass/40'}`}>
                        <a.icon size={16} className="mt-0.5 shrink-0 text-brass-light" />
                        <span className="min-w-0"><b className="block font-medium text-[13px] truncate">{a.title}</b><span className="block text-[11.5px] text-faint truncate">{a.sub}</span></span>
                    </button>
                ))}
                {!actions.length && <p className="text-sm text-muted">Rien d'urgent. Lancez le radar pour trouver de nouvelles cibles.</p>}
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint mt-3">Objectif du mois</p>
                <div className="flex items-center gap-4">
                    <svg width="86" height="86" viewBox="0 0 86 86" className="shrink-0">
                        <circle cx="43" cy="43" r="36" stroke="#25324C" strokeWidth="7" fill="none" />
                        <circle cx="43" cy="43" r="36" stroke="#C9A45C" strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={`${c * Math.min(1, won / goal)} ${c}`} transform="rotate(-90 43 43)" />
                        <text x="43" y="48" textAnchor="middle" fill="#ECEFF4" fontSize="17" fontWeight="600">{won}/{goal}</text>
                    </svg>
                    <div className="text-[12.5px] text-muted">
                        <b className="font-medium text-ink">Rendez-vous et mandats</b><br />
                        {won} ce mois-ci sur
                        <select value={goal} onChange={e => onGoal(Number(e.target.value))} aria-label="Objectif du mois" className="mx-1 rounded border border-line bg-raised px-1 text-ink">
                            {[3, 5, 8, 10, 15, 20].map(g => <option key={g} value={g}>{g}</option>)}
                        </select>
                        visés.
                    </div>
                </div>
            </div>
        </div>
    );
}
