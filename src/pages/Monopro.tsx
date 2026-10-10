import { useEffect, useState } from 'react';
import { Building2, Copy, ExternalLink, FileText, Loader2, MapPin, Printer, Sparkles, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, DPE_COLORS, DpeBadge, eur, type DPEClass } from '../ui';
import { AgentPageForm, errorDetail, type AgentPageData } from './Contacts';

// Whole buildings held by a single owner (BDNB): the "Immeubles entiers" mode
// of the prospection map, and the sheet of a building with its owner.

export interface MonoOwner { siren: string; name: string | null; legal_form: string | null; city: string | null }

export interface MonoBuilding {
    id: string;
    address: string | null;
    lat: number;
    lon: number;
    nb_log: number;
    levels: number | null;
    year_built: number | null;
    owner: MonoOwner | null;
    owner_share: number | null;
    dpe_label: DPEClass | null;
    dpe_date: string | null;
    dpe_count: number | null;
    dpe_fg: number | null;
    last_sale_date: string | null;
    last_sale_price: number | null;
    last_sale_units: number | null;
    signal_score: number | null;
    signal_level: SignalLevel | null;
}

export type SignalLevel = 'fort' | 'moyen' | 'faible';

interface SignalSummary { titre: string; lecture: string; approche: string; probabilite: 'faible' | 'moyenne' | 'forte' }

interface Signal {
    score: number;
    level: SignalLevel | null;
    events: { date: string | null; kind: string; label: string; url: string | null }[];
    checked_on: string | null;
    summary: SignalSummary | null;
    can_explain: boolean;
}

const SIGNAL_STYLE: Record<SignalLevel, string> = {
    fort: 'border-coral/60 bg-coral/10 text-coral',
    moyen: 'border-brass/60 bg-brass/10 text-brass-light',
    faible: 'border-line bg-raised text-muted',
};

export function SignalBadge({ level }: { level: SignalLevel }) {
    return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${SIGNAL_STYLE[level]}`}>Signal {level}</span>;
}

interface Company {
    name: string | null;
    address: string | null;
    active: boolean;
    created: string | null;
    officers: { name: string; role: string | null; company: boolean }[];
    url: string;
}

interface Sheet extends MonoBuilding {
    company: Company | null;
    portfolio: { id: string; address: string | null; nb_log: number; dpe_label: DPEClass | null; lat: number; lon: number }[];
    signal: Signal | null;
}

// BODACC notices of the owner, and what they mean, written by Claude
function SignalPanel({ buildingId, signal }: { buildingId: string; signal: Signal }) {
    const { authedFetch } = useAccount();
    const [summary, setSummary] = useState<SignalSummary | null>(signal.summary);
    const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');
    useEffect(() => {
        if (summary || !signal.can_explain) return;
        let cancelled = false;
        setState('loading');
        authedFetch(`/api/monopro/${encodeURIComponent(buildingId)}/signal/explain`, { method: 'POST' })
            .then(async r => { if (!r.ok) throw new Error(); return r.json(); })
            .then(s => { if (!cancelled) { setSummary(s); setState('idle'); } })
            .catch(() => { if (!cancelled) setState('error'); });
        return () => { cancelled = true; };
    }, [buildingId, summary, signal.can_explain, authedFetch]);

    return (
        <div className="rounded-xl border border-coral/40 bg-coral/5 p-4">
            <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-ink">Signaux de vente au BODACC</p>
                {signal.level && <SignalBadge level={signal.level} />}
            </div>
            <ul className="mt-2 space-y-1 text-sm">
                {signal.events.slice(0, 6).map((e, i) => (
                    <li key={i} className="flex items-center justify-between gap-3">
                        <span className="text-ink-soft">{e.label}</span>
                        <span className="shrink-0 text-xs text-faint">
                            {dateFr(e.date)}
                            {e.url && <a href={e.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-brass-light hover:underline">annonce</a>}
                        </span>
                    </li>
                ))}
            </ul>
            <div className="mt-3 border-t border-line/60 pt-3">
                <p className="text-xs text-faint flex items-center gap-1.5"><Sparkles size={12} className="text-brass" />Lecture par l'IA</p>
                {summary ? (
                    <div className="mt-1.5 space-y-2 text-sm">
                        <p className="text-ink">{summary.titre}</p>
                        <p className="text-ink-soft">{summary.lecture}</p>
                        <p className="text-ink-soft"><span className="text-faint">Approche : </span>{summary.approche}</p>
                        <p className="text-xs text-faint">Probabilité de mise en vente sous 12 mois : <span className="text-ink-soft">{summary.probabilite}</span></p>
                    </div>
                ) : state === 'loading' ? (
                    <p className="mt-1.5 text-sm text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Analyse des annonces…</p>
                ) : (
                    <p className="mt-1.5 text-sm text-muted">{state === 'error' ? "L'analyse n'est pas disponible pour le moment." : 'Analyse non disponible.'}</p>
                )}
            </div>
            <p className="mt-3 text-xs text-faint">
                Annonces légales publiques (BODACC, DILA){signal.checked_on ? `, vérifiées le ${dateFr(signal.checked_on)}` : ''}. Des indices, pas des certitudes :
                vérifiez l'annonce avant toute démarche, et restez discret.
            </p>
        </div>
    );
}

export const NO_DPE_COLOR = '#6C778C';
export const monoColor = (b: Pick<MonoBuilding, 'dpe_label'>) => (b.dpe_label ? DPE_COLORS[b.dpe_label].bg : NO_DPE_COLOR);
const year = (iso: string | null) => (iso ? iso.slice(0, 4) : '');
const dateFr = (iso: string | null) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '');
// "SCI DU BRUNIOL" already carries its legal form
const withForm = (form: string | null, name: string | null) =>
    !form || (name || '').toUpperCase().startsWith(`${form.toUpperCase()} `) ? (name || '') : `${form} ${name || ''}`.trim();
const ownerLabel = (b: MonoBuilding) => (b.owner ? withForm(b.owner.legal_form, b.owner.name) : 'Propriétaire non identifié');

export function MonoproList({ buildings, onFocus, onOpen }: {
    buildings: MonoBuilding[];
    onFocus: (b: MonoBuilding) => void;
    onOpen: (b: MonoBuilding) => void;
}) {
    return (
        <ul className="max-h-[60vh] overflow-y-auto divide-y divide-line/70">
            {buildings.slice(0, 300).map(b => (
                <li key={b.id} className="px-4 py-3">
                    <button type="button" onClick={() => onFocus(b)} className="flex items-start gap-3 text-left w-full">
                        {b.dpe_label ? <DpeBadge label={b.dpe_label} size="sm" /> : (
                            <span className="h-7 w-7 shrink-0 rounded-md bg-raised text-faint flex items-center justify-center"><Building2 size={14} /></span>
                        )}
                        <span className="min-w-0">
                            <span className="block text-sm text-ink truncate">{b.address || 'Adresse non renseignée'}</span>
                            <span className="block text-xs text-faint">
                                {b.nb_log} logements · <span className={b.owner ? 'text-ink-soft' : ''}>{ownerLabel(b)}</span>
                                {b.last_sale_date ? ` · vendu en ${year(b.last_sale_date)}` : ''}
                            </span>
                            {b.signal_level && b.signal_level !== 'faible' && <span className="mt-1 block"><SignalBadge level={b.signal_level} /></span>}
                        </span>
                    </button>
                    <button type="button" onClick={() => onOpen(b)} className="mt-2 ml-10 text-xs text-brass-light hover:text-ink">
                        {b.owner ? 'Fiche du propriétaire et courrier' : "Fiche de l'immeuble"}
                    </button>
                </li>
            ))}
        </ul>
    );
}

export function ownerLetter(s: Sheet, agency: AgentPageData) {
    const company = s.company?.name || s.owner?.name || 'la société propriétaire';
    const signature = [agency.agent_name, agency.agency_name, agency.phone, agency.email].filter(Boolean).join('\n');
    const optOut = agency.email || agency.phone || "l'agence";
    const dpe = s.dpe_fg ? `\n\nPar ailleurs, ${s.dpe_fg > 1 ? `${s.dpe_fg} des logements de l'immeuble sont classés` : "un logement de l'immeuble est classé"} F ou G au diagnostic de performance énergétique : ${s.dpe_fg > 1 ? 'ils sont' : 'il est'} progressivement interdit${s.dpe_fg > 1 ? 's' : ''} à la location (G depuis 2025, F en 2028). C'est souvent le bon moment pour envisager une cession.` : '';
    return `${company}
À l'attention de la gérance
${s.company?.address || s.owner?.city || ''}

Madame, Monsieur,

Votre société est propriétaire de l'immeuble situé ${s.address || ''} (${s.nb_log} logements).

Notre agence accompagne les propriétaires d'immeubles de rapport du secteur : estimation de la valeur de l'immeuble entier ou lot par lot, mise en relation avec des investisseurs, ou vente à la découpe.${dpe}

Vous trouverez joint un dossier sur votre immeuble : performance énergétique des logements, obligations à venir, travaux à prévoir et valeur estimée, en bloc et lot par lot.

Je serais heureux de vous proposer une estimation gratuite et confidentielle, sans engagement.

${signature}

Nous vous écrivons à partir de données publiques : base nationale des bâtiments (CSTB), fichiers des propriétaires personnes morales (DGFiP) et registre des entreprises. Pour ne plus recevoir de courrier de notre part, indiquez-le-nous (${optOut}) : nous en tiendrons compte.`;
}

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

// A building of the map, or the building at the position of a building DPE
export type SheetTarget = { id: string } | { near: { lat: number; lon: number; address: string } };

export function MonoproSheet({ target, onClose, onFocus }: { target: SheetTarget; onClose: () => void; onFocus: (lat: number, lon: number) => void }) {
    const { authedFetch } = useAccount();
    const [sheet, setSheet] = useState<Sheet | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notFound, setNotFound] = useState(false);
    const [agency, setAgency] = useState<AgentPageData | null>(null);
    const [writing, setWriting] = useState(false);
    const [copied, setCopied] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [dossierError, setDossierError] = useState<string | null>(null);
    const [needsAgency, setNeedsAgency] = useState(false);

    // Sale dossier (PDF): units, rental bans, works, value, obligations
    const downloadDossier = async () => {
        if (!sheet) return;
        setDownloading(true);
        setDossierError(null);
        try {
            const res = await authedFetch(`/api/monopro/${encodeURIComponent(sheet.id)}/dossier`);
            if (res.status === 409) {
                setNeedsAgency(true);
                if (!agency) setAgency(await authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {})).catch(() => ({})));
                return;
            }
            if (!res.ok) throw new Error(await errorDetail(res, "Le dossier n'a pas pu être généré."));
            const url = URL.createObjectURL(await res.blob());
            const a = document.createElement('a');
            a.href = url;
            a.download = res.headers.get('content-disposition')?.match(/filename=([^;]+)/)?.[1] || 'Dossier_immeuble.pdf';
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            setDossierError((e as Error).message);
        } finally {
            setDownloading(false);
        }
    };

    useEffect(() => {
        setSheet(null);
        setError(null);
        setNotFound(false);
        const fail = async (res: Response) => { throw new Error((await res.json().catch(() => ({}))).detail || 'Fiche indisponible.'); };
        (async () => {
            let id = 'id' in target ? target.id : null;
            if (!id && 'near' in target) {
                const res = await authedFetch(`/api/monopro/near?lat=${target.near.lat}&lon=${target.near.lon}`);
                if (res.status === 404) { setNotFound(true); return; }
                if (!res.ok) await fail(res);
                id = (await res.json()).id;
            }
            const res = await authedFetch(`/api/monopro/${encodeURIComponent(id!)}`);
            if (!res.ok) await fail(res);
            setSheet(await res.json());
        })().catch(e => setError((e as Error).message));
    }, [target, authedFetch]);

    useEffect(() => {
        if (writing && !agency) authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {})).then(setAgency).catch(() => setAgency({}));
    }, [writing, agency, authedFetch]);

    const text = sheet && agency?.agency_name ? ownerLetter(sheet, agency) : '';
    const copy = async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* unavailable */ }
    };
    const print = () => {
        const w = window.open('', '_blank');
        if (!w) return;
        const paragraphs = escapeHtml(text).split('\n\n').map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
        w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Courrier</title>
<style>body{font-family:Georgia,serif;font-size:12pt;line-height:1.5;max-width:17cm;margin:2cm auto;color:#111}
p:first-child{margin-left:9cm}p:last-child{font-size:9pt;color:#555;margin-top:2em}</style></head><body>${paragraphs}</body></html>`);
        w.document.close();
        w.focus();
        w.print();
    };

    return (
        <div className="fixed inset-0 z-[1000] bg-canvas/80 backdrop-blur-sm flex items-start sm:items-center justify-center p-4 overflow-y-auto" role="dialog" aria-modal="true">
            <Card className="w-full max-w-2xl p-5 sm:p-6 relative">
                <button type="button" onClick={onClose} className="absolute top-4 right-4 text-faint hover:text-ink" aria-label="Fermer"><X size={18} /></button>
                {notFound && 'near' in target ? (
                    <div className="pr-8 space-y-3">
                        <p className="text-xs text-brass tracking-wide">Immeuble</p>
                        <h2 className="text-xl text-ink">{target.near.address}</h2>
                        <p className="text-sm text-muted">
                            Cet immeuble n'est pas détenu en entier par une société privée : c'est une copropriété (immatriculée ou non), un
                            immeuble de bailleur social ou d'organisme public, ou il appartient à des particuliers, dont l'identité n'est pas publique.
                        </p>
                        <p className="text-sm text-muted">Les immeubles détenus par une SCI ou une autre société sont dans l'onglet « Immeubles entiers » de la carte.</p>
                    </div>
                ) : error ? <p className="text-sm text-coral">{error}</p> : !sheet ? <Loader2 className="animate-spin text-brass" /> : (
                    <div className="space-y-5">
                        <div className="pr-8">
                            <p className="text-xs text-brass tracking-wide">Immeuble entier · {sheet.nb_log} logements</p>
                            <h2 className="mt-1 text-xl text-ink">{sheet.address || 'Adresse non renseignée'}</h2>
                        </div>

                        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                            <div><dt className="text-xs text-faint">Logements</dt><dd className="text-ink">{sheet.nb_log}{sheet.levels ? ` · ${sheet.levels} niveaux` : ''}</dd></div>
                            {sheet.year_built && <div><dt className="text-xs text-faint">Construction</dt><dd className="text-ink">{sheet.year_built}</dd></div>}
                            <div>
                                <dt className="text-xs text-faint">DPE</dt>
                                <dd className="text-ink flex items-center gap-2">
                                    {sheet.dpe_label ? <DpeBadge label={sheet.dpe_label} size="sm" /> : 'Aucun publié'}
                                    {sheet.dpe_fg ? <span className="text-xs text-coral">{sheet.dpe_fg} en F ou G</span> : null}
                                </dd>
                            </div>
                            <div>
                                <dt className="text-xs text-faint">Dernière vente</dt>
                                <dd className="text-ink">{sheet.last_sale_date ? `${dateFr(sheet.last_sale_date)}${sheet.last_sale_price ? ` · ${eur(sheet.last_sale_price)}` : ''}` : 'Aucune depuis 2014'}</dd>
                            </div>
                        </dl>

                        <div className="rounded-xl border border-line p-4">
                            <p className="text-xs text-faint">Propriétaire</p>
                            {sheet.owner ? (
                                <>
                                    <p className="mt-1 text-ink">{withForm(sheet.owner.legal_form, sheet.company?.name || sheet.owner.name)}</p>
                                    <p className="text-sm text-muted">
                                        SIREN {sheet.owner.siren}{sheet.company?.created ? ` · créée en ${year(sheet.company.created)}` : ''}
                                        {sheet.company && !sheet.company.active ? ' · société fermée' : ''}
                                    </p>
                                    <p className="mt-2 text-sm text-ink-soft">Siège : {sheet.company?.address || sheet.owner.city || 'non renseigné'}</p>
                                    {!!sheet.company?.officers.length && (
                                        <ul className="mt-2 text-sm text-ink-soft space-y-0.5">
                                            {sheet.company.officers.map(o => <li key={o.name}>{o.name} <span className="text-faint">· {o.role || 'dirigeant'}</span></li>)}
                                        </ul>
                                    )}
                                    {sheet.company && (
                                        <a href={sheet.company.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-brass-light hover:underline">
                                            <ExternalLink size={12} />Annuaire des entreprises
                                        </a>
                                    )}
                                </>
                            ) : (
                                <p className="mt-1 text-sm text-muted">
                                    Aucune société n'est propriétaire de cet immeuble hors copropriété : il appartient très probablement à un particulier
                                    (ou à une indivision), dont l'identité n'est pas publique. Vous pouvez demander l'identité du propriétaire d'un bien
                                    précis au service de la publicité foncière (formulaire 3233-SD, payant, nombre de demandes limité), ou laisser un
                                    courrier à l'adresse de l'immeuble.
                                </p>
                            )}
                        </div>

                        {sheet.signal && <SignalPanel buildingId={sheet.id} signal={sheet.signal} />}

                        {sheet.portfolio.length > 0 && (
                            <div>
                                <p className="text-sm font-medium text-ink-soft">Autres immeubles de cette société ({sheet.portfolio.length})</p>
                                <ul className="mt-1 divide-y divide-line/60">
                                    {sheet.portfolio.slice(0, 12).map(p => (
                                        <li key={p.id}>
                                            <button type="button" onClick={() => { onFocus(p.lat, p.lon); onClose(); }}
                                                className="w-full py-2 flex items-center justify-between gap-3 text-left text-sm hover:text-ink">
                                                <span className="flex items-center gap-2 min-w-0 text-ink-soft"><MapPin size={12} className="shrink-0 text-brass" /><span className="truncate">{p.address}</span></span>
                                                <span className="shrink-0 text-xs text-faint">{p.nb_log} log.{p.dpe_label ? ` · ${p.dpe_label}` : ''}</span>
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {needsAgency && agency && !agency.agency_name ? (
                            <div>
                                <p className="text-sm text-muted mb-3">Renseignez d'abord votre agence : elle signe le dossier et le courrier.</p>
                                <AgentPageForm initial={agency} onSaved={a => { setAgency(a); setNeedsAgency(false); }} />
                            </div>
                        ) : (
                            <div className="rounded-xl border border-brass/40 bg-brass/5 p-4">
                                <p className="text-sm text-ink">Dossier de cession à remettre au propriétaire</p>
                                <p className="mt-1 text-xs text-muted">
                                    Logements interdits à la location et calendrier, gel des loyers, travaux à prévoir, valeur lot par lot et en bloc,
                                    décote liée au DPE, audit obligatoire à la vente : à vos couleurs, en PDF.
                                </p>
                                <Button onClick={downloadDossier} disabled={downloading} className="mt-3 h-10 w-full">
                                    {downloading ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}Télécharger le dossier (PDF)
                                </Button>
                                {dossierError && <p className="mt-2 text-xs text-coral">{dossierError}</p>}
                            </div>
                        )}

                        {sheet.owner && !writing && (
                            <Button variant="secondary" onClick={() => setWriting(true)} className="w-full">Préparer un courrier à la société</Button>
                        )}
                        {writing && (!agency ? <Loader2 className="animate-spin text-brass" /> : !agency.agency_name ? (
                            <div>
                                <p className="text-sm text-muted mb-3">Renseignez d'abord votre agence : elle signe le courrier.</p>
                                <AgentPageForm initial={agency} onSaved={setAgency} />
                            </div>
                        ) : (
                            <div className="space-y-3">
                                <textarea readOnly value={text} aria-label="Texte du courrier" className="h-72 w-full rounded-xl border border-line bg-raised p-3 text-sm text-ink-soft" />
                                <div className="flex flex-wrap gap-2">
                                    <Button onClick={print} className="h-10"><Printer size={14} />Imprimer</Button>
                                    <Button variant="secondary" onClick={copy} className="h-10"><Copy size={14} />{copied ? 'Texte copié' : 'Copier le texte'}</Button>
                                </div>
                            </div>
                        ))}

                        <p className="text-xs text-faint">
                            Sources publiques : base nationale des bâtiments (CSTB, Licence Ouverte), fichiers des personnes morales propriétaires (DGFiP),
                            Annuaire des entreprises (INSEE, RNE), annonces légales (BODACC). Courrier postal uniquement, avec l'origine des données et le droit d'opposition
                            (article 14 des CGV). Un immeuble absent du registre peut être une petite copropriété non immatriculée.
                        </p>
                    </div>
                )}
            </Card>
        </div>
    );
}
