import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { Copy, Download, Loader2, Printer, X } from 'lucide-react';
import { useAccount } from '../account';
import { Button, Card, type DPEClass } from '../ui';
import { AgentPageForm, errorDetail, type AgentPageData } from './Contacts';

const RENTAL_BAN: Partial<Record<DPEClass, string>> = {
    G: "ne peut plus faire l'objet d'un nouveau bail depuis le 1er janvier 2025",
    F: "ne pourra plus faire l'objet d'un nouveau bail à partir du 1er janvier 2028",
    E: "ne pourra plus faire l'objet d'un nouveau bail à partir du 1er janvier 2034",
};

const escapeHtml = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

export interface LetterTarget {
    address: string;
    label: DPEClass;
    dpeNumber: string;
}

export function letterText(t: LetterTarget, agency: AgentPageData, url: string) {
    const signature = [agency.agent_name, agency.agency_name, agency.phone, agency.email].filter(Boolean).join('\n');
    const optOut = agency.email || agency.phone || "l'agence";
    return `Madame, Monsieur,

Je m'adresse aux propriétaires du ${t.address}.

Le diagnostic de performance énergétique de ce logement, publié en données ouvertes par l'ADEME, le classe en ${t.label}. Avec la loi Climat et Résilience, un logement classé ${t.label} ${RENTAL_BAN[t.label] ?? 'est concerné par le calendrier de rénovation'}. Ce classement pèse aussi sur le prix de vente.

J'ai préparé pour vous une première estimation : travaux possibles, aides, reste à charge et valeur de votre bien après rénovation. Pour la consulter, scannez le QR code ci-joint ou rendez-vous sur :
${url}

Si vous le souhaitez, vous pourrez m'y laisser vos coordonnées pour une estimation détaillée, sans engagement.

Si vous êtes locataire, merci de transmettre ce courrier à votre propriétaire.

${signature}

Ce courrier est adressé au logement : nous ne connaissons pas votre identité. L'adresse provient des données publiques de l'ADEME (DPE). Pour ne plus recevoir de courrier de notre part, indiquez-le-nous (${optOut}) : nous retirerons cette adresse de nos envois.`;
}

export default function LetterDialog({ target, onClose }: { target: LetterTarget; onClose: () => void }) {
    const { authedFetch } = useAccount();
    const [agency, setAgency] = useState<AgentPageData | null>(null);
    const [url, setUrl] = useState<string | null>(null);
    const [qr, setQr] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        authedFetch('/api/agent-page').then(r => (r.ok ? r.json() : {})).then(setAgency).catch(() => setAgency({}));
    }, [authedFetch]);

    // One link per dwelling, created once the agency is known
    useEffect(() => {
        if (!agency?.agency_name) return;
        (async () => {
            try {
                const res = await authedFetch('/api/prospection/links', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dpe_number: target.dpeNumber, address: target.address, label: target.label }),
                });
                if (!res.ok) throw new Error(await errorDetail(res, 'Le lien n\'a pas pu être créé.'));
                const { code } = await res.json();
                const link = `${window.location.origin}/l/${code}`;
                setUrl(link);
                setQr(await QRCode.toDataURL(link, { margin: 1, width: 600, errorCorrectionLevel: 'M' }));
            } catch (e) {
                setError((e as Error).message);
            }
        })();
    }, [agency?.agency_name, authedFetch, target]);

    const text = agency && url ? letterText(target, agency, url) : '';

    const copy = async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* unavailable */ }
    };

    const downloadQr = () => {
        if (!qr) return;
        const a = document.createElement('a');
        a.href = qr;
        a.download = `qr-${target.dpeNumber}.png`;
        a.click();
    };

    const print = () => {
        const w = window.open('', '_blank');
        if (!w || !qr) return;
        const paragraphs = escapeHtml(text).split('\n\n').map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
        w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Courrier ${escapeHtml(target.address)}</title>
<style>body{font-family:Georgia,serif;font-size:12pt;line-height:1.5;max-width:17cm;margin:2cm auto;color:#111}
.qr{float:right;margin:0 0 1em 1.5em;text-align:center;font:9pt sans-serif;color:#555}.qr img{width:3.5cm;height:3.5cm;display:block}
p:last-child{font-size:9pt;color:#555;margin-top:2em}</style></head>
<body><div class="qr"><img src="${qr}" alt="QR code">Scannez-moi</div>${paragraphs}</body></html>`);
        w.document.close();
        w.focus();
        w.print();
    };

    return (
        <div className="fixed inset-0 z-[1000] bg-canvas/80 backdrop-blur-sm flex items-start sm:items-center justify-center p-4 overflow-y-auto" role="dialog" aria-modal="true">
            <Card className="w-full max-w-2xl p-5 sm:p-6 relative">
                <button type="button" onClick={onClose} className="absolute top-4 right-4 text-faint hover:text-ink" aria-label="Fermer"><X size={18} /></button>
                <h2 className="text-xl text-ink pr-8">Courrier pour le {target.address}</h2>

                {!agency ? (
                    <Loader2 className="mt-4 animate-spin text-brass" />
                ) : !agency.agency_name ? (
                    <div className="mt-4">
                        <p className="text-sm text-muted mb-4">Renseignez d'abord votre agence : elle apparaîtra sur la page que le propriétaire ouvrira avec le QR code.</p>
                        <AgentPageForm initial={agency} onSaved={setAgency} />
                    </div>
                ) : error ? (
                    <p className="mt-4 text-sm text-coral">{error}</p>
                ) : !url || !qr ? (
                    <Loader2 className="mt-4 animate-spin text-brass" />
                ) : (
                    <div className="mt-4 grid sm:grid-cols-[1fr_180px] gap-5">
                        <textarea readOnly value={text} aria-label="Texte du courrier"
                            className="h-80 w-full rounded-xl border border-line bg-raised p-3 text-sm text-ink-soft" />
                        <div className="text-center">
                            <img src={qr} alt="QR code vers la page du logement" className="w-full rounded-lg bg-white p-2" />
                            <p className="mt-2 text-xs text-faint break-all">{url}</p>
                        </div>
                        <div className="sm:col-span-2 flex flex-wrap gap-2">
                            <Button onClick={print} className="h-10"><Printer size={14} />Imprimer le courrier</Button>
                            <Button variant="secondary" onClick={copy} className="h-10"><Copy size={14} />{copied ? 'Texte copié' : 'Copier le texte'}</Button>
                            <Button variant="secondary" onClick={downloadQr} className="h-10"><Download size={14} />QR code (PNG)</Button>
                        </div>
                        <p className="sm:col-span-2 text-xs text-faint">
                            Le propriétaire qui scanne le QR code voit la simulation de son logement à vos couleurs et peut demander à être rappelé :
                            sa demande arrive dans <a href="/contacts" className="underline">Contacts</a>.
                        </p>
                    </div>
                )}
            </Card>
        </div>
    );
}
