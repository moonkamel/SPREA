import { useState } from 'react';
import QRCode from 'qrcode';
import { ArrowDown, ArrowUp, Footprints, Loader2, Map as MapIcon, Printer, QrCode, Route, Trash2, UserSearch } from 'lucide-react';
import { useAccount } from '../account';
import { Button, type DPEClass } from '../ui';
import { letterText } from './LetterDialog';
import { errorDetail, type AgentPageData } from './Contacts';

// Tools of the Prospection dashboard: who is likely to sell (signals) and the
// letterbox round (optimised order, letters printed in one go).

export interface SignalReason { points: number; label: string; kind: string }
export interface SignalItem {
    address: string; lat: number; lon: number; insee: string | null;
    score: number; level: 'fort' | 'moyen' | 'faible'; reasons: SignalReason[];
    label: DPEClass | null; dpe_date: string | null; dwellings: number; kind: string | null; surface: number | null;
    dpe_number: string | null; long_held: boolean; last_sale: { date: string; price: number } | null;
    near_sales: number; near_sale: { date: string; price_m2: number; street: string | null } | null;
}
export interface SignalsResult { items: SignalItem[]; total: number; truncated: boolean; dvf_since: number | null; strong: number }
export interface TourStop { key: string; address: string; lat: number; lon: number; label?: DPEClass | null; dpeNumber?: string | null }

export const SIGNAL_COLORS = { fort: '#FF6B4A', moyen: '#E3C98F', faible: '#6C778C' } as const;

const shortDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('fr-FR') : '');
const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

// --- Round ---

const TOUR_KEY = 'sprea-tournee';
export function loadTour(): TourStop[] {
    try { return JSON.parse(localStorage.getItem(TOUR_KEY) || '[]'); } catch { return []; }
}
export function saveTour(stops: TourStop[]) {
    try { localStorage.setItem(TOUR_KEY, JSON.stringify(stops)); } catch { /* private mode: kept for this visit */ }
}

export function metres(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
    const r = 6371000, p1 = a.lat * Math.PI / 180, p2 = b.lat * Math.PI / 180;
    const dp = p2 - p1, dl = (b.lon - a.lon) * Math.PI / 180;
    const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * r * Math.asin(Math.sqrt(h));
}

export function tourLength(stops: TourStop[]) {
    let d = 0;
    for (let i = 1; i < stops.length; i++) d += metres(stops[i - 1], stops[i]);
    return d;
}

/** Shortest round found from the first stop: nearest neighbour, then 2-opt. */
export function optimise(stops: TourStop[]): TourStop[] {
    if (stops.length < 3) return stops;
    const left = stops.slice(1);
    const route = [stops[0]];
    while (left.length) {
        const last = route[route.length - 1];
        let best = 0;
        left.forEach((s, i) => { if (metres(last, s) < metres(last, left[best])) best = i; });
        route.push(left.splice(best, 1)[0]);
    }
    let improved = true;
    while (improved) {
        improved = false;
        for (let i = 1; i < route.length - 2; i++) {
            for (let k = i + 1; k < route.length - 1; k++) {
                const before = metres(route[i - 1], route[i]) + metres(route[k], route[k + 1]);
                const after = metres(route[i - 1], route[k]) + metres(route[i], route[k + 1]);
                if (after + 1 < before) {
                    route.splice(i, k - i + 1, ...route.slice(i, k + 1).reverse());
                    improved = true;
                }
            }
        }
    }
    return route;
}

// Walking: straight lines lengthened by a third for the streets, 4.5 km/h, one minute per letterbox
export const walkMinutes = (stops: TourStop[]) => Math.round(tourLength(stops) * 1.33 / 75 + stops.length);

/** Google Maps itinerary of the round (it takes up to 9 stops between the ends). */
export function mapsUrl(stops: TourStop[]) {
    const pt = (s: TourStop) => `${s.lat.toFixed(6)},${s.lon.toFixed(6)}`;
    const first = stops[0], last = stops[Math.min(stops.length, 11) - 1];
    const middle = stops.slice(1, Math.min(stops.length, 11) - 1).map(pt).join('|');
    return `https://www.google.com/maps/dir/?api=1&travelmode=walking&origin=${pt(first)}&destination=${pt(last)}${middle ? `&waypoints=${encodeURIComponent(middle)}` : ''}`;
}

const LETTER_STYLE = `body{font-family:Georgia,serif;font-size:12pt;line-height:1.5;color:#111;margin:0}
.page{max-width:17cm;margin:2cm auto;page-break-after:always}.page:last-child{page-break-after:auto}
.qr{float:right;margin:0 0 1em 1.5em;text-align:center;font:9pt sans-serif;color:#555}.qr img{width:3.5cm;height:3.5cm;display:block}
.small{font-size:9pt;color:#555;margin-top:2em}`;

function letterPage(text: string, qr: string) {
    const paragraphs = escapeHtml(text).split('\n\n').map((p, i, all) => `<p${i === all.length - 1 ? ' class="small"' : ''}>${p.replace(/\n/g, '<br>')}</p>`).join('');
    return `<div class="page"><div class="qr"><img src="${qr}" alt="QR code">Scannez-moi</div>${paragraphs}</div>`;
}

function printPages(title: string, pages: string[]) {
    const w = window.open('', '_blank');
    if (!w) return false;
    w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title><style>${LETTER_STYLE}</style></head><body>${pages.join('')}</body></html>`);
    w.document.close();
    w.focus();
    w.print();
    return true;
}

export function TourPanel({ stops, onChange, onFocus, onDelivered }: {
    stops: TourStop[];
    onChange: (stops: TourStop[]) => void;
    onFocus: (s: TourStop) => void;
    // Letters left in the boxes: the follow-up of each DPE goes to « courrier »
    onDelivered: (stops: TourStop[]) => void;
}) {
    const { authedFetch } = useAccount();
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const withLetter = stops.filter(s => s.dpeNumber && s.label);
    const move = (i: number, d: number) => {
        const next = [...stops];
        [next[i], next[i + d]] = [next[i + d], next[i]];
        onChange(next);
    };
    const printAll = async () => {
        setBusy(true);
        setMessage(null);
        try {
            const agency: AgentPageData = await authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {}));
            if (!agency.agency_name) throw new Error('Renseignez d\'abord votre agence (ouvrez un courrier depuis une adresse).');
            const pages: string[] = [];
            for (const s of withLetter) {
                const res = await authedFetch('/api/prospection/links', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dpe_number: s.dpeNumber, address: s.address, label: s.label }),
                });
                if (!res.ok) throw new Error(await errorDetail(res, 'Un lien n\'a pas pu être créé.'));
                const { code } = await res.json();
                const url = `${window.location.origin}/l/${code}`;
                const qr = await QRCode.toDataURL(url, { margin: 1, width: 600, errorCorrectionLevel: 'M' });
                pages.push(letterPage(letterText({ address: s.address, label: s.label!, dpeNumber: s.dpeNumber! }, agency, url), qr));
            }
            if (!printPages('Tournée de courriers', pages)) throw new Error('Autorisez les fenêtres pour imprimer.');
            setMessage(`${pages.length} courrier${pages.length > 1 ? 's' : ''} prêt${pages.length > 1 ? 's' : ''}, dans l'ordre de la tournée.`);
        } catch (e) {
            setMessage((e as Error).message);
        } finally {
            setBusy(false);
        }
    };
    return (
        <div className="flex-1 overflow-y-auto">
            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Tournée de boîtage</p>
                <h2 className="text-[19px] text-ink">{stops.length ? `${stops.length} adresse${stops.length > 1 ? 's' : ''}` : 'Votre tournée'}</h2>
                {stops.length > 1 && (
                    <p className="mt-1 text-xs text-muted flex items-center gap-1.5">
                        <Footprints size={13} className="text-brass-light" />
                        {(tourLength(stops) * 1.33 / 1000).toFixed(1).replace('.', ',')} km à pied, environ {walkMinutes(stops)} min
                    </p>
                )}
                {stops.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                        <Button variant="secondary" className="h-9 px-3 text-xs" onClick={() => onChange(optimise(stops))} disabled={stops.length < 3}>
                            <Route size={14} />Optimiser l'ordre
                        </Button>
                        <Button className="h-9 px-3 text-xs" onClick={printAll} disabled={busy || !withLetter.length}>
                            {busy ? <Loader2 size={14} className="animate-spin" /> : <Printer size={14} />}Imprimer les {withLetter.length} courriers
                        </Button>
                        <a href={mapsUrl(stops)} target="_blank" rel="noreferrer"
                            className="h-9 px-3 rounded-[10px] border border-line text-xs text-muted hover:text-ink inline-flex items-center gap-1.5">
                            <MapIcon size={14} />Itinéraire{stops.length > 11 ? ' (11 premières)' : ''}
                        </a>
                        <Button variant="secondary" className="h-9 px-3 text-xs" onClick={() => onDelivered(withLetter)} disabled={!withLetter.length}>
                            Courriers déposés
                        </Button>
                    </div>
                )}
                {message && <p className="mt-2 text-xs text-faint">{message}</p>}
            </div>
            {!stops.length ? (
                <p className="px-[18px] py-4 text-sm text-muted">
                    Ajoutez des adresses depuis Signaux, Récents, le radar ou la fiche DPE (bouton « Tournée ») : SPREA calcule l'ordre le plus
                    court, l'itinéraire à pied, et imprime tous les courriers avec QR code dans l'ordre de passage.
                </p>
            ) : (
                <ol className="divide-y divide-line/70">
                    {stops.map((s, i) => (
                        <li key={s.key} className="px-[18px] py-2.5 flex items-center gap-3">
                            <span className="h-6 w-6 shrink-0 rounded-full bg-brass/15 text-brass-light text-xs flex items-center justify-center">{i + 1}</span>
                            <button type="button" onClick={() => onFocus(s)} className="min-w-0 flex-1 text-left">
                                <span className="block text-sm text-ink truncate">{s.address}</span>
                                <span className="block text-[11px] text-faint">{s.label ? `DPE ${s.label}` : 'Sans DPE'}{s.dpeNumber ? ' · courrier avec QR code' : ''}</span>
                            </button>
                            <div className="flex items-center text-faint">
                                <button type="button" aria-label="Monter" disabled={i === 0} onClick={() => move(i, -1)} className="p-1 hover:text-ink disabled:opacity-30"><ArrowUp size={14} /></button>
                                <button type="button" aria-label="Descendre" disabled={i === stops.length - 1} onClick={() => move(i, 1)} className="p-1 hover:text-ink disabled:opacity-30"><ArrowDown size={14} /></button>
                                <button type="button" aria-label="Retirer" onClick={() => onChange(stops.filter(x => x.key !== s.key))} className="p-1 hover:text-coral"><Trash2 size={14} /></button>
                            </div>
                        </li>
                    ))}
                </ol>
            )}
            {stops.length > 0 && (
                <button type="button" onClick={() => onChange([])} className="mx-[18px] my-3 text-xs text-faint hover:text-coral">Vider la tournée</button>
            )}
        </div>
    );
}

// --- Signals ---

export function SignalsPanel({ data, loading, zoomOk, filter, onFilter, onFocus, inTour, onTour, onLetter, onOwner }: {
    data: SignalsResult | null;
    loading: boolean;
    zoomOk: boolean;
    filter: 'all' | 'fort' | 'held' | 'fresh';
    onFilter: (f: 'all' | 'fort' | 'held' | 'fresh') => void;
    onFocus: (s: SignalItem) => void;
    inTour: (key: string) => boolean;
    onTour: (s: SignalItem) => void;
    onLetter: (s: SignalItem) => void;
    onOwner: (s: SignalItem) => void;
}) {
    const items = (data?.items || []).filter(s => filter === 'all' || (filter === 'fort' ? s.level === 'fort'
        : filter === 'held' ? s.long_held : s.reasons.some(r => r.kind === 'dpe' && r.points >= 28)));
    const filters: [typeof filter, string][] = [['all', 'Tous'], ['fort', 'Signal fort'], ['held', 'Propriétaires de longue date'], ['fresh', 'DPE < 6 mois']];
    return (
        <div className="flex-1 overflow-y-auto">
            <div className="px-[18px] pt-4 pb-3 border-b border-line">
                <p className="text-[10px] tracking-[0.16em] uppercase text-faint">Probabilité de vente</p>
                <h2 className="text-[19px] text-ink">
                    {!zoomOk ? 'Zoomez sur un quartier' : loading && !data ? 'Analyse des adresses…' : data ? `${data.strong} ${data.strong > 1 ? 'signaux forts' : 'signal fort'} sur ${data.total} adresses` : '…'}
                </h2>
                <p className="mt-1 text-xs text-faint">DPE récent, location bloquée, propriétaire de longue date, ventes voisines, société en difficulté.</p>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {filters.map(([k, l]) => (
                        <button key={k} type="button" onClick={() => onFilter(k)}
                            className={`h-7 px-2.5 rounded-full border text-xs ${filter === k ? 'border-brass/60 bg-brass/10 text-brass-light' : 'border-line text-muted hover:text-ink'}`}>{l}</button>
                    ))}
                </div>
            </div>
            <ul className="divide-y divide-line/70">
                {items.slice(0, 200).map(s => {
                    const key = `${s.lat},${s.lon}`;
                    return (
                        <li key={key} className="px-[18px] py-3">
                            <button type="button" onClick={() => onFocus(s)} className="flex items-start gap-3 text-left w-full">
                                <span className="h-9 w-9 shrink-0 rounded-full border-2 flex items-center justify-center text-[13px] font-semibold"
                                    style={{ borderColor: SIGNAL_COLORS[s.level], color: SIGNAL_COLORS[s.level] }}>{s.score}</span>
                                <span className="min-w-0">
                                    <span className="block text-sm text-ink truncate">{s.address}</span>
                                    <span className="block text-xs text-faint">
                                        {[s.kind, s.dwellings > 1 ? `${s.dwellings} logements` : s.surface ? `${Math.round(s.surface)} m²` : null,
                                          s.label ? `DPE ${s.label} du ${shortDate(s.dpe_date)}` : null].filter(Boolean).join(' · ')}
                                    </span>
                                </span>
                            </button>
                            <ul className="mt-1.5 ml-12 space-y-0.5">
                                {s.reasons.slice(0, 3).map(r => (
                                    <li key={r.label} className={`text-[11.5px] ${r.points < 0 ? 'text-faint' : 'text-muted'}`}>
                                        <span className={r.points < 0 ? 'text-coral' : 'text-brass-light'}>{r.points > 0 ? `+${r.points}` : r.points}</span> {r.label}
                                    </li>
                                ))}
                            </ul>
                            <div className="mt-2 ml-12 flex flex-wrap gap-x-3 gap-y-1.5 text-xs">
                                <button type="button" disabled={inTour(key)} onClick={() => onTour(s)}
                                    className="text-brass-light hover:text-ink disabled:text-faint flex items-center gap-1"><Route size={12} />{inTour(key) ? 'Dans la tournée' : 'Tournée'}</button>
                                {s.dpe_number && s.label && (
                                    <button type="button" onClick={() => onLetter(s)} className="text-muted hover:text-ink flex items-center gap-1"><QrCode size={12} />Courrier</button>
                                )}
                                <button type="button" onClick={() => onOwner(s)} className="text-muted hover:text-ink flex items-center gap-1"><UserSearch size={12} />Propriétaire</button>
                            </div>
                        </li>
                    );
                })}
            </ul>
            {data && (
                <p className="px-[18px] py-3 text-[11px] text-faint border-t border-line">
                    Score sur 100 à partir de données publiques : DPE de l'ADEME (2 dernières années), ventes DVF{data.dvf_since ? ` depuis ${data.dvf_since}` : ''},
                    signaux BODACC des sociétés propriétaires. Un indice, pas une certitude.{data.truncated ? ' Zone dense : zoomez pour tout voir.' : ''}
                </p>
            )}
        </div>
    );
}

