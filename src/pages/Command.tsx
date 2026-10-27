import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { ArrowLeft, ArrowRight, Bell, Building2, Calculator, Eye, FileText, Loader2, Lock, Map as MapIcon, QrCode, Radar, Search, Star, UserSearch, Users, Workflow } from 'lucide-react';
import { useAccount } from '../account';
import { Link, navigate } from '../router';
import { useSeo } from '../seo';
import { TourHost, useAutoTour } from '../tour';
import { Button, DPE_COLORS, eur, eurRange, type DPEClass } from '../ui';
import LetterDialog, { type LetterTarget } from './LetterDialog';
import OwnerRequestDialog, { type OwnerTarget } from './OwnerRequestDialog';
import { DossierDialog, FOLLOW_UPS, dpeAge, type Audience, type FollowUp, type Opportunity, type OpportunityScan } from './Opportunities';

// SPREA Command: the agent's prospecting cockpit. The radar of their area
// (recent F and G DPE, each valued), the targets ranked by score, one target
// with every figure and every action, and the follow-up board with what is
// due today. Built only on SPREA's data: nothing here is made up.

type View = 'radar' | 'cible' | 'suivi';
interface Center { lat: number; lon: number; label: string }
interface PipelineItem { number: string; status: FollowUp; address: string | null; updated_at: string | null; mine: boolean }
interface EstimateLead { id: string; name: string; address: string; city: string | null; lat: number | null; lon: number | null; project: string; status: string; phone: string | null; created_at: string }
interface Kpis { newDpe: number | null; signals: number | null; strongSignals: number | null }

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

export default function CommandPage() {
    useSeo({ title: 'SPREA Command · Votre cockpit de prospection', noindex: true });
    const { session, me, authedFetch, openLogin, config } = useAccount();
    const [view, setView] = useState<View>('radar');
    const [center, setCenter] = useState<Center | null>(() => {
        try { return JSON.parse(sessionStorage.getItem(CENTER_KEY) || 'null'); } catch { return null; }
    });
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
    // First visit straight to Command: the welcome tour from its Command steps
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
    }, [ranked, selected, leads, focus, mapReady]);

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
            { label: 'Carte classique', hint: 'Tous les DPE, immeubles entiers', run: () => navigate('/prospection') },
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
                    <h1 className="mt-4 text-3xl text-ink">SPREA Command</h1>
                    <p className="mt-3 text-muted">Le cockpit de prospection : le radar de votre secteur, vos cibles classées par score, chaque bien chiffré et toutes les actions à portée de clavier. Inclus dans la formule Pro.</p>
                    <div className="mt-6 flex justify-center gap-3">
                        {!session && <Button onClick={() => openLogin('Connectez-vous pour ouvrir SPREA Command.')} disabled={!config?.auth_enabled}>Se connecter</Button>}
                        <Button variant={session ? 'primary' : 'secondary'} onClick={() => navigate('/demo#command')}>Voir la démo</Button>
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
            <TourHost screen="command" />
            {/* Top bar */}
            <header className="h-14 shrink-0 flex items-center gap-3 sm:gap-5 px-3 sm:px-5 border-b border-line bg-gradient-to-b from-[#0D1424] to-canvas">
                <Link to="/" className="font-serif text-[21px] font-semibold tracking-wide">SPREA</Link>
                <span className="hidden md:inline text-xs text-muted">Command · <b className="font-medium text-brass-light">{center?.label || '…'}</b> · rayon 1,5 km</span>
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
                <Link to="/prospection" className="hidden sm:flex items-center gap-1.5 rounded-[10px] border border-line px-3 h-9 text-xs text-muted hover:text-ink"><MapIcon size={14} />Carte classique</Link>
            </header>

            <div className="flex-1 min-h-0 flex flex-col-reverse lg:flex-row">
                {/* Rail */}
                <nav className="shrink-0 flex lg:flex-col items-center justify-around lg:justify-start gap-1.5 lg:w-[68px] border-t lg:border-t-0 lg:border-r border-line bg-[#0B1120] py-1.5 lg:pt-3.5" aria-label="Vues">
                    {([
                        ['radar', Radar, 'Radar', () => backToRadar()],
                        ['cible', Star, 'Cible', () => { const t = current?.o || ranked[0]?.o; if (t) focus(t); }],
                        ['suivi', Workflow, 'Suivi', () => setView('suivi')],
                    ] as const).map(([v, Icon, label, go]) => (
                        <button key={v} type="button" onClick={go} aria-current={view === v ? 'page' : undefined} data-tour={v === 'suivi' ? 'cmd-suivi' : undefined}
                            className={`relative w-12 h-[52px] rounded-xl flex flex-col items-center justify-center gap-0.5 text-[10px] ${view === v ? 'text-brass-light bg-brass/10 lg:shadow-[inset_2px_0_0_#C9A45C]' : 'text-faint hover:text-ink'}`}>
                            <Icon size={19} strokeWidth={1.6} />{label}
                            {v === 'suivi' && due.length > 0 && <span className="absolute top-1 right-1 h-4 min-w-4 px-1 rounded-full bg-coral text-[9px] text-white flex items-center justify-center">{due.length}</span>}
                        </button>
                    ))}
                    {([
                        ['/prospection?mode=immeubles', Building2, 'Immeubles', 0],
                        ['/alertes', Bell, 'Alertes', 0],
                        ['/contacts', Users, 'Leads', newLeads.length],
                    ] as const).map(([to, Icon, label, badge]) => (
                        <Link key={to} to={to} className="relative w-12 h-[52px] rounded-xl flex flex-col items-center justify-center gap-0.5 text-[10px] text-faint hover:text-ink">
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
