import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, FileText, Info, Loader2, Sparkles, Trash2, Upload, X } from 'lucide-react';
import { useAccount } from '../account';
import { navigate } from '../router';
import { useSeo } from '../seo';
import { Button, Card, eur } from '../ui';
import { errorDetail } from './Contacts';
import { SiteFooter, SiteHeader } from './site';

// Copropriété documents read by Claude (api/copro_docs.py): PV d'AG, carnet
// d'entretien, pré-état daté... -> what a buyer must know before signing.

type Level = 'alerte' | 'attention' | 'info';
type Risk = 'faible' | 'modéré' | 'élevé';

interface Result {
    copropriete: { nom: string | null; adresse: string | null; syndic: string | null; lots: string | null };
    documents: { fichier: string; nature: string; date: string | null; lisible: boolean }[];
    synthese: string;
    niveau_risque: Risk;
    travaux_votes: { objet: string; montant: number | null; date_vote: string | null; appels_de_fonds: string | null; etat: string; source: string }[];
    travaux_a_venir: { objet: string; estimation: string | null; horizon: string | null; source: string }[];
    procedures: { objet: string; role_syndicat: string; montant: number | null; etat: string; source: string }[];
    finances: { budget_previsionnel: number | null; fonds_travaux: number | null; impayes_coproprietaires: number | null;
        dettes_fournisseurs: number | null; commentaire: string | null; source: string | null };
    obligations: { plan_pluriannuel: string | null; dtg: string | null; dpe_collectif: string | null };
    vie_copropriete: string[];
    vigilance: { niveau: Level; point: string; source: string }[];
    questions_syndic: string[];
    documents_manquants: string[];
}

interface Analysis {
    id: string;
    address: string | null;
    status: string;
    created_at: string;
    files: { name: string; size: number }[];
    synthese: string | null;
    niveau_risque: Risk | null;
    result?: Result | null;
}

const TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
const MAX_FILE = 20 * 1024 * 1024;
const MAX_TOTAL = 22 * 1024 * 1024;
const MAX_FILES = 8;
const mb = (n: number) => `${(n / 1024 / 1024).toFixed(n < 1024 * 1024 ? 2 : 1).replace('.', ',')} Mo`;
const dateFr = (iso: string) => new Date(iso).toLocaleDateString('fr-FR');

const RISK_STYLE: Record<Risk, string> = {
    faible: 'border-sage/50 bg-sage/10 text-sage',
    modéré: 'border-brass/60 bg-brass/10 text-brass-light',
    élevé: 'border-coral/60 bg-coral/10 text-coral',
};
const LEVEL_ICON: Record<Level, JSX.Element> = {
    alerte: <AlertTriangle size={14} className="text-coral shrink-0 mt-0.5" />,
    attention: <AlertTriangle size={14} className="text-brass-light shrink-0 mt-0.5" />,
    info: <Info size={14} className="text-faint shrink-0 mt-0.5" />,
};

function RiskBadge({ risk }: { risk: Risk }) {
    return <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs ${RISK_STYLE[risk]}`}>Risque {risk}</span>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div>
            <h3 className="text-sm font-medium text-ink-soft">{title}</h3>
            <div className="mt-2">{children}</div>
        </div>
    );
}

const Src = ({ s }: { s: string | null }) => (s ? <span className="text-faint text-xs"> · {s}</span> : null);

function ResultView({ analysis, onDelete, onPdf }: { analysis: Analysis; onDelete: () => void; onPdf: () => void }) {
    const r = analysis.result!;
    const f = r.finances;
    const money = (label: string, v: number | null) => (v == null ? null : <div key={label}><dt className="text-xs text-faint">{label}</dt><dd className="text-ink">{eur(v)}</dd></div>);
    const obligations = [['Plan pluriannuel de travaux', r.obligations.plan_pluriannuel], ['Diagnostic technique global', r.obligations.dtg],
        ['DPE collectif / audit', r.obligations.dpe_collectif]].filter(([, v]) => v);
    return (
        <Card className="p-5 sm:p-6 space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="text-xs text-brass tracking-wide flex items-center gap-1.5"><Sparkles size={12} />Synthèse des documents de copropriété</p>
                    <h2 className="mt-1 text-xl text-ink">{analysis.address || r.copropriete.adresse || 'Copropriété'}</h2>
                    <p className="text-sm text-muted">
                        {[r.copropriete.nom, r.copropriete.syndic && `syndic ${r.copropriete.syndic}`, r.copropriete.lots && `${r.copropriete.lots} lots`].filter(Boolean).join(' · ')}
                    </p>
                </div>
                <RiskBadge risk={r.niveau_risque} />
            </div>
            <p className="text-ink-soft leading-relaxed">{r.synthese}</p>

            {r.vigilance.length > 0 && (
                <Section title="Points de vigilance">
                    <ul className="space-y-2 text-sm">
                        {r.vigilance.map((v, i) => <li key={i} className="flex gap-2">{LEVEL_ICON[v.niveau]}<span className="text-ink-soft">{v.point}<Src s={v.source} /></span></li>)}
                    </ul>
                </Section>
            )}

            {r.travaux_votes.length > 0 && (
                <Section title="Travaux votés">
                    <ul className="divide-y divide-line/60 text-sm">
                        {r.travaux_votes.map((w, i) => (
                            <li key={i} className="py-2 flex justify-between gap-4">
                                <span className="text-ink-soft">
                                    {w.objet} <span className="text-faint">({w.etat}{w.date_vote ? `, AG du ${w.date_vote}` : ''})</span>
                                    {w.appels_de_fonds && <span className="block text-xs text-muted">Appels de fonds : {w.appels_de_fonds}</span>}
                                    <Src s={w.source} />
                                </span>
                                <span className="shrink-0 text-ink">{w.montant != null ? eur(w.montant) : '–'}</span>
                            </li>
                        ))}
                    </ul>
                </Section>
            )}

            {r.travaux_a_venir.length > 0 && (
                <Section title="Travaux à venir (non votés)">
                    <ul className="space-y-1.5 text-sm">
                        {r.travaux_a_venir.map((w, i) => (
                            <li key={i} className="text-ink-soft">{w.objet}
                                <span className="text-muted">{[w.estimation, w.horizon].filter(Boolean).length ? ` · ${[w.estimation, w.horizon].filter(Boolean).join(' · ')}` : ''}</span>
                                <Src s={w.source} />
                            </li>
                        ))}
                    </ul>
                </Section>
            )}

            {(f.budget_previsionnel != null || f.fonds_travaux != null || f.impayes_coproprietaires != null || f.dettes_fournisseurs != null || f.commentaire) && (
                <Section title="Finances du syndicat">
                    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                        {[money('Budget annuel', f.budget_previsionnel), money('Fonds de travaux', f.fonds_travaux),
                            money('Charges impayées', f.impayes_coproprietaires), money('Dettes fournisseurs', f.dettes_fournisseurs)]}
                    </dl>
                    {f.commentaire && <p className="mt-2 text-sm text-muted">{f.commentaire}<Src s={f.source} /></p>}
                </Section>
            )}

            {r.procedures.length > 0 && (
                <Section title="Procédures">
                    <ul className="space-y-1.5 text-sm">
                        {r.procedures.map((p, i) => (
                            <li key={i} className="text-ink-soft">{p.objet} <span className="text-muted">· syndicat {p.role_syndicat}{p.montant != null ? ` · ${eur(p.montant)}` : ''} · {p.etat}</span><Src s={p.source} /></li>
                        ))}
                    </ul>
                </Section>
            )}

            {(obligations.length > 0 || r.vie_copropriete.length > 0) && (
                <Section title="Obligations et vie de la copropriété">
                    <ul className="space-y-1 text-sm text-ink-soft list-disc pl-5">
                        {obligations.map(([k, v]) => <li key={k}>{k} : {v}</li>)}
                        {r.vie_copropriete.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                </Section>
            )}

            {r.questions_syndic.length > 0 && (
                <Section title="À demander au syndic avant le compromis">
                    <ul className="space-y-1 text-sm text-ink-soft list-disc pl-5">{r.questions_syndic.map((q, i) => <li key={i}>{q}</li>)}</ul>
                </Section>
            )}
            {r.documents_manquants.length > 0 && (
                <Section title="Documents manquants">
                    <ul className="space-y-1 text-sm text-muted list-disc pl-5">{r.documents_manquants.map((q, i) => <li key={i}>{q}</li>)}</ul>
                </Section>
            )}

            <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={onPdf} className="h-10"><FileText size={14} />Synthèse PDF à vos couleurs</Button>
                <Button variant="secondary" onClick={onDelete} className="h-10"><Trash2 size={14} />Supprimer</Button>
            </div>
            <p className="text-xs text-faint">
                Documents analysés : {r.documents.map(d => `${d.fichier}${d.date ? ` (${d.date})` : ''}${d.lisible ? '' : ' – illisible'}`).join(', ')}.
                Synthèse établie par une intelligence artificielle (Claude, Anthropic) à partir des seuls documents fournis : elle ne remplace
                ni leur lecture, ni le pré-état daté, ni l'avis du notaire. Les documents ont été supprimés après l'analyse.
            </p>
        </Card>
    );
}

export default function CoproDocsPage() {
    const { session, me, config, openLogin, authedFetch } = useAccount();
    useSeo({ title: 'Documents de copropriété · SPREA', noindex: true });
    const params = new URLSearchParams(window.location.search);
    const [address, setAddress] = useState(params.get('adresse') || '');
    const [files, setFiles] = useState<File[]>([]);
    const [step, setStep] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [history, setHistory] = useState<Analysis[]>([]);
    const [quota, setQuota] = useState<{ used: number; limit: number } | null>(null);
    const [enabled, setEnabled] = useState(true);
    const [current, setCurrent] = useState<Analysis | null>(null);
    const [locked, setLocked] = useState(false);
    const input = useRef<HTMLInputElement>(null);

    const load = useCallback(async () => {
        if (!session) return;
        const res = await authedFetch('/api/copro-docs');
        if (res.status === 402) { setLocked(true); return; }
        if (!res.ok) return;
        const data = await res.json();
        setHistory(data.analyses);
        setQuota(data.quota);
        setEnabled(data.enabled);
    }, [session, authedFetch]);
    useEffect(() => { load().catch(() => {}); }, [load]);

    const add = (list: FileList | null) => {
        if (!list) return;
        setError(null);
        const picked = [...files, ...Array.from(list)].slice(0, MAX_FILES);
        const bad = picked.find(f => !TYPES.includes(f.type));
        if (bad) { setError(`« ${bad.name} » : seuls les PDF et les photos (JPEG, PNG, WebP) sont acceptés.`); return; }
        const big = picked.find(f => f.size > MAX_FILE);
        if (big) { setError(`« ${big.name} » dépasse 20 Mo.`); return; }
        setFiles(picked);
    };
    const total = files.reduce((n, f) => n + f.size, 0);

    const analyze = async () => {
        setError(null);
        setCurrent(null);
        try {
            setStep('Préparation…');
            const res = await authedFetch('/api/copro-docs/uploads', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address: address.trim() || null, files: files.map(f => ({ name: f.name, size: f.size, type: f.type })) }),
            });
            if (!res.ok) throw new Error(await errorDetail(res, "L'envoi a échoué."));
            const { id, uploads } = await res.json() as { id: string; uploads: { url: string }[] };
            for (let i = 0; i < files.length; i++) {
                setStep(`Envoi des documents (${i + 1}/${files.length})…`);
                const up = await fetch(uploads[i].url, { method: 'PUT', headers: { 'Content-Type': files[i].type }, body: files[i] });
                if (!up.ok) throw new Error(`« ${files[i].name} » n'a pas pu être envoyé.`);
            }
            setStep("Lecture des documents par l'IA : 1 à 3 minutes selon leur longueur…");
            const out = await authedFetch(`/api/copro-docs/${id}/analyze`, { method: 'POST' });
            if (!out.ok) throw new Error(await errorDetail(out, "L'analyse n'a pas abouti."));
            setCurrent(await out.json());
            setFiles([]);
            load().catch(() => {});
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setStep(null);
        }
    };

    const open = async (a: Analysis) => {
        const res = await authedFetch(`/api/copro-docs/${a.id}`);
        if (res.ok) { setCurrent(await res.json()); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    };
    const remove = async () => {
        if (!current) return;
        await authedFetch(`/api/copro-docs/${current.id}`, { method: 'DELETE' });
        setCurrent(null);
        load().catch(() => {});
    };
    const pdf = async () => {
        if (!current) return;
        const res = await authedFetch(`/api/copro-docs/${current.id}/pdf`);
        if (!res.ok) { setError(await errorDetail(res, 'Le PDF n\'a pas pu être généré.')); return; }
        const url = URL.createObjectURL(await res.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = res.headers.get('content-disposition')?.match(/filename="?([^";]+)/)?.[1] || 'Synthese_copropriete.pdf';
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="min-h-screen flex flex-col bg-canvas">
            <SiteHeader />
            <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 space-y-6">
                <div>
                    <h1 className="text-3xl sm:text-4xl text-ink">Documents de copropriété</h1>
                    <p className="mt-2 text-muted max-w-3xl">
                        Déposez les PV des dernières assemblées générales, le carnet d'entretien ou le pré-état daté : l'IA en extrait les travaux votés
                        et à venir, les appels de fonds, les procédures, les impayés, les points de vigilance et les questions à poser au syndic.
                    </p>
                </div>

                {!session ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Connectez-vous pour analyser des documents</p>
                        <Button className="mt-4" onClick={() => openLogin()} disabled={!config?.auth_enabled}>Se connecter</Button>
                    </Card>
                ) : locked || (me && !me.is_pro) ? (
                    <Card className="p-5">
                        <p className="text-ink font-medium">Réservé aux abonnés</p>
                        <Button className="mt-4" onClick={() => navigate('/tarifs')}>Voir les formules</Button>
                    </Card>
                ) : (
                    <>
                        {current?.result && <ResultView analysis={current} onDelete={remove} onPdf={pdf} />}

                        <Card className="p-5 sm:p-6 space-y-4">
                            <h2 className="text-xl text-ink">{current ? 'Nouvelle analyse' : 'Analyser des documents'}</h2>
                            {!enabled && <p className="text-sm text-coral">L'analyse de documents n'est pas encore activée sur ce site.</p>}
                            <label className="block">
                                <span className="text-xs text-faint">Adresse de l'immeuble (facultatif)</span>
                                <input value={address} onChange={e => setAddress(e.target.value)} maxLength={200} placeholder="12 rue Nationale, Lille"
                                    className="mt-1 h-11 w-full rounded-xl border border-line bg-raised px-3 text-sm text-ink" />
                            </label>
                            <div onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); add(e.dataTransfer.files); }}
                                onClick={() => input.current?.click()} role="button" tabIndex={0}
                                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') input.current?.click(); }}
                                className="rounded-xl border-2 border-dashed border-line hover:border-brass/60 p-6 text-center cursor-pointer">
                                <Upload className="mx-auto text-brass" size={22} />
                                <p className="mt-2 text-sm text-ink-soft">Glissez vos PDF ou photos ici, ou cliquez pour les choisir</p>
                                <p className="text-xs text-faint">{MAX_FILES} fichiers, 20 Mo par fichier et 22 Mo au total au maximum</p>
                                <input ref={input} type="file" multiple accept=".pdf,image/jpeg,image/png,image/webp" className="hidden"
                                    onChange={e => { add(e.target.files); e.target.value = ''; }} />
                            </div>
                            {files.length > 0 && (
                                <ul className="divide-y divide-line/60 text-sm">
                                    {files.map((f, i) => (
                                        <li key={i} className="py-2 flex items-center justify-between gap-3">
                                            <span className="truncate text-ink-soft">{f.name}</span>
                                            <span className="shrink-0 flex items-center gap-3 text-xs text-faint">{mb(f.size)}
                                                <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Retirer ${f.name}`} className="hover:text-ink"><X size={14} /></button>
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                            {total > MAX_TOTAL && <p className="text-sm text-coral">22 Mo au total au maximum : analysez les documents en deux fois.</p>}
                            {error && <p className="text-sm text-coral">{error}</p>}
                            {step ? (
                                <p className="text-sm text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin text-brass" />{step}</p>
                            ) : (
                                <Button onClick={analyze} disabled={!files.length || total > MAX_TOTAL || !enabled} className="w-full">
                                    <Sparkles size={16} />Analyser {files.length > 1 ? `les ${files.length} documents` : 'le document'}
                                </Button>
                            )}
                            <p className="text-xs text-faint">
                                Les documents sont transmis à notre prestataire d'IA (Anthropic) pour l'analyse puis supprimés : seule la synthèse est conservée,
                                jusqu'à ce que vous la supprimiez. Les noms des copropriétaires ne sont pas repris.
                                {quota ? ` ${quota.used} analyse${quota.used > 1 ? 's' : ''} sur ${quota.limit} ce mois-ci.` : ''}
                            </p>
                        </Card>

                        {history.length > 0 && (
                            <Card className="p-5 sm:p-6">
                                <h2 className="text-xl text-ink">Vos analyses</h2>
                                <ul className="mt-3 divide-y divide-line/60">
                                    {history.map(a => (
                                        <li key={a.id}>
                                            <button type="button" onClick={() => open(a)} className="w-full py-3 text-left flex items-start justify-between gap-3 hover:text-ink">
                                                <span className="min-w-0">
                                                    <span className="block text-sm text-ink truncate">{a.address || a.files.map(f => f.name).join(', ')}</span>
                                                    <span className="block text-xs text-faint truncate">{dateFr(a.created_at)} · {a.synthese}</span>
                                                </span>
                                                {a.niveau_risque && <RiskBadge risk={a.niveau_risque} />}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </Card>
                        )}
                    </>
                )}
            </main>
            <SiteFooter />
        </div>
    );
}
