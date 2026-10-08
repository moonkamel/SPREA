import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { Loader2, LogOut, Mail, Sparkles, Trash2, User as UserIcon, X } from 'lucide-react';

// --- Types ---

interface PublicConfig {
    auth_enabled: boolean;
    supabase_url: string | null;
    supabase_anon_key: string | null;
    billing_enabled: boolean;
    report_price: string | null;
    pro_price: string | null;
}

interface ReportSummary {
    id: string;
    address: string;
    status: 'pending' | 'paid' | 'included';
    created_at: string;
}

interface Me {
    email: string | null;
    is_pro: boolean;
    subscription_status: string | null;
    subscription_current_period_end: string | null;
    has_billing_account: boolean;
    reports: ReportSummary[];
}

export interface ReportRequest {
    meta: {
        address: string;
        year?: number | null;
        ademe_dpe_number?: string | null;
        building_type?: string | null;
        construction_period?: string | null;
    };
    simulation: object;
}

interface AccountContextValue {
    config: PublicConfig | null;
    session: Session | null;
    me: Me | null;
    requestReport: (req: ReportRequest) => Promise<void>;
    startSubscription: () => void;
    openLogin: (reason?: string) => void;
    openAccount: () => void;
}

// A report asked for before signing in: kept across the magic link round trip
const PENDING_KEY = 'sprea_pending_report';

const savePending = (req: ReportRequest) => {
    try { localStorage.setItem(PENDING_KEY, JSON.stringify(req)); } catch { /* storage unavailable */ }
};
const loadPending = (): ReportRequest | null => {
    try { return JSON.parse(localStorage.getItem(PENDING_KEY) || 'null'); } catch { return null; }
};
const clearPending = () => {
    try { localStorage.removeItem(PENDING_KEY); } catch { /* storage unavailable */ }
};

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

const AccountContext = createContext<AccountContextValue | null>(null);

export const useAccount = () => {
    const ctx = useContext(AccountContext);
    if (!ctx) throw new Error('useAccount must be used inside AccountProvider');
    return ctx;
};

// --- Provider ---

export function AccountProvider({ children }: { children: ReactNode }) {
    const [config, setConfig] = useState<PublicConfig | null>(null);
    const [session, setSession] = useState<Session | null>(null);
    const [me, setMe] = useState<Me | null>(null);
    const [loginReason, setLoginReason] = useState<string | null>(null);
    const [showAccount, setShowAccount] = useState(false);
    const [showDelete, setShowDelete] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);
    const [pending, setPending] = useState<ReportRequest | null>(null);
    // Purchase waiting for the CGV acceptance
    const [purchase, setPurchase] = useState<{ kind: 'report'; req: ReportRequest } | { kind: 'pro' } | null>(null);
    const supabase = useRef<SupabaseClient | null>(null);

    // Fresh access token (supabase-js refreshes it when needed)
    const authedFetch = useCallback(async (url: string, init: RequestInit = {}) => {
        const { data } = await supabase.current!.auth.getSession();
        const headers = new Headers(init.headers);
        if (data.session) headers.set('Authorization', `Bearer ${data.session.access_token}`);
        return fetch(url, { ...init, headers });
    }, []);

    const errorMessage = async (res: Response) => {
        try { return (await res.json()).detail || `Erreur ${res.status}`; } catch { return `Erreur ${res.status}`; }
    };

    const refreshMe = useCallback(async (): Promise<Me | null> => {
        if (!supabase.current) return null;
        const res = await authedFetch('/api/me');
        if (!res.ok) return null;
        const data: Me = await res.json();
        setMe(data);
        return data;
    }, [authedFetch]);

    const downloadReport = useCallback(async (id: string) => {
        const res = await authedFetch(`/api/reports/${id}/pdf`);
        if (!res.ok) { setNotice(await errorMessage(res)); return; }
        const disposition = res.headers.get('content-disposition') || '';
        const filename = disposition.match(/filename=([^;]+)/)?.[1] || 'Rapport_SPREA.pdf';
        const url = URL.createObjectURL(await res.blob());
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }, [authedFetch]);

    const createReport = useCallback(async (req: ReportRequest, acceptTerms: boolean) => {
        const res = await authedFetch('/api/reports', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...req, accept_terms: acceptTerms }),
        });
        if (!res.ok) { setNotice(await errorMessage(res)); return; }
        const data = await res.json();
        if (data.checkout_url) {
            window.location.assign(data.checkout_url);
            return;
        }
        await downloadReport(data.id);
        refreshMe();
    }, [authedFetch, downloadReport, refreshMe]);

    const subscribe = useCallback(async () => {
        const res = await authedFetch('/api/billing/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ accept_terms: true }),
        });
        if (!res.ok) { setNotice(await errorMessage(res)); return; }
        window.location.assign((await res.json()).checkout_url);
    }, [authedFetch]);

    const requestReport = useCallback(async (req: ReportRequest) => {
        if (!config?.auth_enabled) { setNotice("Les comptes ne sont pas encore disponibles."); return; }
        if (!session) {
            savePending(req);
            setLoginReason('Connectez-vous pour obtenir votre rapport PDF. Votre simulation sera conservée.');
            return;
        }
        const account = me || await refreshMe();
        if (account?.is_pro) {
            await createReport(req, false);
            return;
        }
        setPurchase({ kind: 'report', req });
    }, [config, session, me, refreshMe, createReport]);

    const startSubscription = useCallback(() => {
        if (!config?.auth_enabled || !config.billing_enabled) { setNotice("L'abonnement n'est pas encore disponible."); return; }
        if (!session) { setLoginReason("Connectez-vous pour souscrire à l'abonnement Pro."); return; }
        if (me?.is_pro) { setShowAccount(true); return; }
        setShowAccount(false);
        setPurchase({ kind: 'pro' });
    }, [config, session, me]);

    // Back from Stripe Checkout: wait until the payment is confirmed
    const handleCheckoutReturn = useCallback(async () => {
        const params = new URLSearchParams(window.location.search);
        const checkout = params.get('checkout');
        const reportId = params.get('report');
        if (!checkout) return;
        window.history.replaceState({}, '', window.location.pathname);

        if (checkout === 'cancel' || checkout === 'pro_cancel') {
            setNotice('Paiement annulé.');
            return;
        }
        if (checkout === 'success' && reportId) {
            setNotice('Paiement reçu, préparation de votre rapport…');
            for (let i = 0; i < 15; i++) {
                const res = await authedFetch(`/api/reports/${reportId}`);
                if (res.ok && (await res.json()).status !== 'pending') {
                    await downloadReport(reportId);
                    setNotice('Votre rapport a été téléchargé. Il reste disponible dans « Mon compte ».');
                    refreshMe();
                    return;
                }
                await sleep(2000);
            }
            setNotice('Paiement en cours de confirmation. Votre rapport sera disponible dans « Mon compte ».');
        }
        if (checkout === 'pro_success') {
            setNotice('Activation de votre abonnement Pro…');
            for (let i = 0; i < 15; i++) {
                if ((await refreshMe())?.is_pro) {
                    setNotice('Votre abonnement Pro est actif : vos rapports sont désormais inclus.');
                    return;
                }
                await sleep(2000);
            }
            setNotice("Abonnement en cours d'activation, il apparaîtra dans « Mon compte » d'ici quelques instants.");
        }
    }, [authedFetch, downloadReport, refreshMe]);

    // Init: public config, then Supabase session
    useEffect(() => {
        let unsubscribe = () => { };
        fetch('/api/config')
            .then(res => res.json())
            .then(async (cfg: PublicConfig) => {
                setConfig(cfg);
                if (!cfg.auth_enabled || !cfg.supabase_url || !cfg.supabase_anon_key) return;
                // Loaded on demand to keep the initial bundle small
                const { createClient } = await import('@supabase/supabase-js');
                supabase.current = createClient(cfg.supabase_url, cfg.supabase_anon_key);
                const { data } = await supabase.current.auth.getSession();
                setSession(data.session);
                const sub = supabase.current.auth.onAuthStateChange((_event, s) => setSession(s));
                unsubscribe = () => sub.data.subscription.unsubscribe();
            })
            .catch(err => console.error('Config error:', err));
        return () => unsubscribe();
    }, []);

    // Signed in: load the account, handle a Checkout return, offer a pending report
    const signedInUser = session?.user.id;
    useEffect(() => {
        if (!signedInUser) { setMe(null); return; }
        setLoginReason(null);
        refreshMe();
        handleCheckoutReturn();
        setPending(loadPending());
    }, [signedInUser, refreshMe, handleCheckoutReturn]);

    // Checkout return without a session (should not happen, but be explicit)
    useEffect(() => {
        if (config && !config.auth_enabled && new URLSearchParams(window.location.search).get('checkout')) {
            setNotice('Connectez-vous pour retrouver votre rapport.');
        }
    }, [config]);

    const value: AccountContextValue = {
        config, session, me, requestReport, startSubscription,
        openLogin: (reason?: string) => setLoginReason(reason || ''),
        openAccount: () => { setShowAccount(true); refreshMe(); },
    };

    return (
        <AccountContext.Provider value={value}>
            {children}
            {loginReason !== null && supabase.current && (
                <LoginModal reason={loginReason} supabase={supabase.current} onClose={() => setLoginReason(null)} />
            )}
            {showAccount && session && (
                <AccountModal
                    me={me}
                    config={config}
                    onClose={() => setShowAccount(false)}
                    onDownload={downloadReport}
                    onSubscribe={async () => startSubscription()}
                    onPortal={async () => {
                        const res = await authedFetch('/api/billing/portal', { method: 'POST' });
                        if (!res.ok) { setNotice(await errorMessage(res)); return; }
                        window.location.assign((await res.json()).url);
                    }}
                    onLogout={async () => {
                        await supabase.current?.auth.signOut();
                        setShowAccount(false);
                    }}
                    onDelete={() => { setShowAccount(false); setShowDelete(true); }}
                />
            )}
            {showDelete && session && (
                <DeleteAccountModal
                    me={me}
                    onClose={() => setShowDelete(false)}
                    onConfirm={async () => {
                        const res = await authedFetch('/api/me', {
                            method: 'DELETE',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ confirm: true }),
                        });
                        if (!res.ok) { setNotice(await errorMessage(res)); return; }
                        clearPending();
                        setPending(null);
                        setShowDelete(false);
                        await supabase.current?.auth.signOut();
                        setNotice('Votre compte et vos rapports ont été supprimés.');
                    }}
                />
            )}
            {pending && session && (
                <Toast onClose={() => { clearPending(); setPending(null); }}>
                    <span>Reprendre votre rapport pour <b>{pending.meta.address}</b> ?</span>
                    <button
                        onClick={() => { const req = pending; clearPending(); setPending(null); requestReport(req); }}
                        className="ml-3 px-3 py-1.5 rounded-lg bg-white text-slate-900 font-black text-[10px] uppercase tracking-widest"
                    >
                        Obtenir le rapport
                    </button>
                </Toast>
            )}
            {purchase && (
                <PurchaseModal
                    kind={purchase.kind}
                    price={purchase.kind === 'report' ? config?.report_price : config?.pro_price}
                    onClose={() => setPurchase(null)}
                    onConfirm={async () => {
                        if (purchase.kind === 'report') await createReport(purchase.req, true);
                        else await subscribe();
                        setPurchase(null);
                    }}
                />
            )}
            {notice && <Toast onClose={() => setNotice(null)}>{notice}</Toast>}
        </AccountContext.Provider>
    );
}

// --- UI ---

export function AccountButton({ className = '' }: { className?: string }) {
    const { config, session, me, openLogin, openAccount } = useAccount();
    if (!config?.auth_enabled) return null;
    return (
        <button
            onClick={() => (session ? openAccount() : openLogin())}
            className={`h-14 px-6 rounded-2xl bg-white text-slate-700 font-black hover:bg-slate-900 hover:text-white transition-all text-[10px] uppercase tracking-widest border border-slate-200 flex items-center gap-2 ${className}`}
        >
            <UserIcon size={16} />
            {session ? 'Mon compte' : 'Se connecter'}
            {me?.is_pro && <span className="px-1.5 py-0.5 rounded bg-blue-600 text-white text-[8px]">PRO</span>}
        </button>
    );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
    return (
        <div className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-md p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-label={title}>
                <button onClick={onClose} className="absolute top-5 right-5 text-slate-400 hover:text-slate-900" aria-label="Fermer"><X size={20} /></button>
                <h2 className="text-xl font-black text-slate-800 tracking-tight mb-6">{title}</h2>
                {children}
            </div>
        </div>
    );
}

function Toast({ children, onClose }: { children: ReactNode; onClose: () => void }) {
    return (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[110] max-w-[calc(100%-2rem)] bg-slate-900 text-white text-sm rounded-2xl shadow-2xl px-5 py-4 flex items-center gap-3">
            <div className="flex-1 flex items-center flex-wrap gap-y-2">{children}</div>
            <button onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Fermer"><X size={16} /></button>
        </div>
    );
}

function LoginModal({ reason, supabase, onClose }: { reason: string; supabase: SupabaseClient; onClose: () => void }) {
    const [email, setEmail] = useState('');
    const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');

    const send = async (e: React.FormEvent) => {
        e.preventDefault();
        setStatus('sending');
        const { error } = await supabase.auth.signInWithOtp({
            email,
            options: { emailRedirectTo: window.location.origin },
        });
        setStatus(error ? 'error' : 'sent');
    };

    return (
        <Modal title="Connexion" onClose={onClose}>
            {reason && <p className="text-sm text-slate-500 mb-5">{reason}</p>}
            {status === 'sent' ? (
                <div className="text-center py-4">
                    <Mail className="mx-auto text-blue-600 mb-3" size={32} />
                    <p className="font-bold text-slate-800">Lien envoyé à {email}</p>
                    <p className="text-sm text-slate-500 mt-2">Cliquez sur le lien reçu par email pour vous connecter. Pas de mot de passe à retenir.</p>
                </div>
            ) : (
                <form onSubmit={send} className="space-y-4">
                    <input
                        type="email"
                        required
                        autoFocus
                        placeholder="votre@email.fr"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        className="w-full h-14 px-5 rounded-2xl bg-slate-100 font-bold text-slate-900 outline-none border-2 border-transparent focus:border-blue-600 focus:bg-white"
                    />
                    <button type="submit" disabled={status === 'sending'} className="w-full h-14 rounded-2xl bg-blue-600 text-white font-black uppercase text-xs tracking-widest hover:bg-blue-700 flex items-center justify-center gap-2">
                        {status === 'sending' && <Loader2 className="animate-spin" size={16} />}
                        Recevoir un lien de connexion
                    </button>
                    {status === 'error' && <p className="text-sm text-red-600">L'envoi a échoué, vérifiez l'adresse et réessayez.</p>}
                    <p className="text-[10px] text-slate-400 leading-relaxed">
                        Votre email sert uniquement à vous connecter, à conserver vos rapports et à vous envoyer vos factures.{' '}
                        <a href="/confidentialite" target="_blank" rel="noopener" className="underline">Politique de confidentialité</a>
                    </p>
                </form>
            )}
        </Modal>
    );
}

function AccountModal({ me, config, onClose, onDownload, onSubscribe, onPortal, onLogout, onDelete }: {
    me: Me | null;
    config: PublicConfig | null;
    onClose: () => void;
    onDownload: (id: string) => Promise<void>;
    onSubscribe: () => Promise<void>;
    onPortal: () => Promise<void>;
    onLogout: () => Promise<void>;
    onDelete: () => void;
}) {
    const [busy, setBusy] = useState<string | null>(null);
    const run = (key: string, fn: () => Promise<void>) => async () => {
        setBusy(key);
        try { await fn(); } finally { setBusy(null); }
    };
    const periodEnd = me?.subscription_current_period_end
        ? new Date(me.subscription_current_period_end).toLocaleDateString('fr-FR')
        : null;

    return (
        <Modal title="Mon compte" onClose={onClose}>
            {!me ? <Loader2 className="animate-spin text-slate-400" /> : (
                <div className="space-y-6">
                    <p className="text-sm text-slate-500">{me.email}</p>

                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-5">
                        {me.is_pro ? (
                            <>
                                <p className="font-black text-slate-800 flex items-center gap-2"><Sparkles size={16} className="text-blue-600" /> Abonnement Pro actif</p>
                                <p className="text-xs text-slate-500 mt-1">Rapports illimités{periodEnd ? ` · renouvellement le ${periodEnd}` : ''}</p>
                            </>
                        ) : (
                            <>
                                <p className="font-black text-slate-800">Formule gratuite</p>
                                <p className="text-xs text-slate-500 mt-1">
                                    Rapport à l'unité{config?.report_price ? ` : ${config.report_price}` : ''}. Professionnels : rapports illimités avec l'abonnement Pro{config?.pro_price ? ` (${config.pro_price})` : ''}.
                                </p>
                                {config?.billing_enabled && (
                                    <button onClick={run('subscribe', onSubscribe)} className="mt-4 w-full h-12 rounded-xl bg-blue-600 text-white font-black uppercase text-[10px] tracking-widest hover:bg-blue-700 flex items-center justify-center gap-2">
                                        {busy === 'subscribe' && <Loader2 className="animate-spin" size={14} />}
                                        Passer Pro
                                    </button>
                                )}
                            </>
                        )}
                        {me.has_billing_account && (
                            <button onClick={run('portal', onPortal)} className="mt-3 w-full h-10 rounded-xl bg-white border border-slate-200 text-slate-600 font-black uppercase text-[10px] tracking-widest hover:bg-slate-100 flex items-center justify-center gap-2">
                                {busy === 'portal' && <Loader2 className="animate-spin" size={14} />}
                                Factures et abonnement
                            </button>
                        )}
                    </div>

                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Mes rapports</p>
                        {me.reports.length === 0 ? (
                            <p className="text-sm text-slate-400">Aucun rapport pour le moment.</p>
                        ) : (
                            <ul className="space-y-2 max-h-60 overflow-y-auto">
                                {me.reports.map(r => (
                                    <li key={r.id} className="flex items-center justify-between gap-3 text-sm">
                                        <span className="truncate text-slate-700">
                                            {r.address}
                                            <span className="block text-[10px] text-slate-400">{new Date(r.created_at).toLocaleDateString('fr-FR')}</span>
                                        </span>
                                        <button onClick={run(r.id, () => onDownload(r.id))} className="shrink-0 px-3 py-2 rounded-lg bg-blue-50 text-blue-600 font-black text-[10px] uppercase tracking-widest hover:bg-blue-600 hover:text-white flex items-center gap-1">
                                            {busy === r.id && <Loader2 className="animate-spin" size={12} />}
                                            PDF
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    <div className="flex items-center justify-between gap-4">
                        <button onClick={run('logout', onLogout)} className="text-xs font-bold text-slate-400 hover:text-slate-900 flex items-center gap-2">
                            <LogOut size={14} /> Se déconnecter
                        </button>
                        <button onClick={onDelete} className="text-xs font-bold text-slate-400 hover:text-red-600 flex items-center gap-2">
                            <Trash2 size={14} /> Supprimer mon compte
                        </button>
                    </div>
                </div>
            )}
        </Modal>
    );
}

function PurchaseModal({ kind, price, onClose, onConfirm }: {
    kind: 'report' | 'pro';
    price: string | null | undefined;
    onClose: () => void;
    onConfirm: () => Promise<void>;
}) {
    const [accepted, setAccepted] = useState(false);
    const [busy, setBusy] = useState(false);
    const isReport = kind === 'report';
    const cgv = <a href="/cgv" target="_blank" rel="noopener" className="underline text-blue-600">conditions générales de vente</a>;

    return (
        <Modal title={isReport ? 'Obtenir le rapport' : "Passer à l'abonnement Pro"} onClose={onClose}>
            <div className="rounded-2xl bg-slate-50 border border-slate-100 p-5 mb-5">
                <p className="text-2xl font-black text-slate-900">{price || '—'}<span className="text-xs font-bold text-slate-400 ml-2">TTC</span></p>
                <p className="text-xs text-slate-500 mt-1">
                    {isReport
                        ? 'Rapport PDF de ce logement, téléchargeable immédiatement puis à tout moment depuis votre compte. Facture fournie.'
                        : 'Rapports illimités. Abonnement mensuel sans engagement, résiliable à tout moment depuis votre compte.'}
                </p>
            </div>
            <label className="flex items-start gap-3 text-xs text-slate-600 leading-relaxed cursor-pointer">
                <input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600" />
                {isReport ? (
                    <span>J'accepte les {cgv} et je demande l'accès immédiat à mon rapport. Je reconnais perdre mon droit de rétractation dès sa mise à disposition.</span>
                ) : (
                    <span>J'accepte les {cgv} et je demande le démarrage immédiat de l'abonnement. Si j'exerce mon droit de rétractation dans les 14 jours, je reste redevable du montant correspondant au service déjà fourni.</span>
                )}
            </label>
            <button
                disabled={!accepted || busy}
                onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}
                className="mt-6 w-full h-14 rounded-2xl bg-blue-600 text-white font-black uppercase text-xs tracking-widest hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
                {busy && <Loader2 className="animate-spin" size={16} />}
                Continuer vers le paiement
            </button>
            <p className="text-[10px] text-slate-400 text-center mt-3">Paiement sécurisé par Stripe</p>
        </Modal>
    );
}

function DeleteAccountModal({ me, onClose, onConfirm }: {
    me: Me | null;
    onClose: () => void;
    onConfirm: () => Promise<void>;
}) {
    const [understood, setUnderstood] = useState(false);
    const [busy, setBusy] = useState(false);
    const reportCount = me?.reports.length || 0;

    return (
        <Modal title="Supprimer mon compte" onClose={onClose}>
            <ul className="text-sm text-slate-600 leading-relaxed space-y-2 list-disc pl-5 mb-5">
                <li>Votre compte et votre adresse email sont supprimés.</li>
                <li>
                    {reportCount > 0
                        ? <><b>Vos {reportCount} rapport{reportCount > 1 ? 's' : ''}</b> ne pourront plus être téléchargés : enregistrez-les avant de continuer.</>
                        : 'Vos rapports sont supprimés.'}
                </li>
                {me?.is_pro && <li>Votre <b>abonnement Pro est résilié immédiatement</b>, sans remboursement de la période en cours.</li>}
                <li>Les factures et une trace minimale de vos achats (date, montant, version des CGV acceptée) sont conservées pour nos obligations légales, sans vos simulations.</li>
            </ul>
            <label className="flex items-start gap-3 text-xs text-slate-600 cursor-pointer">
                <input type="checkbox" checked={understood} onChange={e => setUnderstood(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-red-600" />
                <span>Je comprends que cette suppression est définitive.</span>
            </label>
            <button
                disabled={!understood || busy}
                onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}
                className="mt-6 w-full h-14 rounded-2xl bg-red-600 text-white font-black uppercase text-xs tracking-widest hover:bg-red-700 disabled:bg-slate-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
                {busy && <Loader2 className="animate-spin" size={16} />}
                Supprimer définitivement
            </button>
            <button onClick={onClose} className="mt-3 w-full text-xs font-bold text-slate-400 hover:text-slate-900">Annuler</button>
        </Modal>
    );
}
