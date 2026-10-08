import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { Button } from './ui';
import { navigate } from './router';
import { Loader2, LogOut, Mail, Sparkles, Trash2, User as UserIcon, X } from 'lucide-react';

// --- Types ---

interface PublicConfig {
    auth_enabled: boolean;
    supabase_url: string | null;
    supabase_anon_key: string | null;
    billing_enabled: boolean;
    report_price: string | null;
    pro_price: string | null;
    // Subscription plans, prices excluding VAT
    plans?: Partial<Record<Plan, string | null>>;
}

export type Plan = 'solo_monthly' | 'solo_yearly';

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
        dpe_date?: string | null;
        city?: string | null;
        postcode?: string | null;
        details?: Record<string, string | null> | null;
        insee_code?: string | null;
        latitude?: number | null;
        longitude?: number | null;
    };
    simulation: object;
}

interface AccountContextValue {
    config: PublicConfig | null;
    session: Session | null;
    me: Me | null;
    requestReport: (req: ReportRequest) => Promise<void>;
    startSubscription: (plan?: Plan) => void;
    openLogin: (reason?: string) => void;
    openAccount: () => void;
    authedFetch: (url: string, init?: RequestInit) => Promise<Response>;
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
    const [purchase, setPurchase] = useState<{ plan: Plan } | null>(null);
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
        await downloadReport(data.id);
        refreshMe();
    }, [authedFetch, downloadReport, refreshMe]);

    const subscribe = useCallback(async (plan: Plan) => {
        const res = await authedFetch('/api/billing/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ accept_terms: true, plan }),
        });
        if (!res.ok) { setNotice(await errorMessage(res)); return; }
        window.location.assign((await res.json()).checkout_url);
    }, [authedFetch]);

    // Reports are included in the subscription
    const requestReport = useCallback(async (req: ReportRequest) => {
        if (!session) {
            savePending(req);
            setLoginReason('Connectez-vous pour obtenir le rapport PDF. La simulation sera conservée.');
            return;
        }
        const account = me || await refreshMe();
        if (!account?.is_pro) { navigate('/tarifs'); return; }
        await createReport(req, false);
    }, [session, me, refreshMe, createReport]);

    const startSubscription = useCallback((plan: Plan = 'solo_monthly') => {
        if (!config?.auth_enabled || !config.billing_enabled) { setNotice("L'abonnement sera disponible très prochainement."); return; }
        if (!session) { setLoginReason("Créez votre compte avec votre email professionnel : vous choisirez ensuite votre formule."); return; }
        if (me?.is_pro) { setShowAccount(true); return; }
        setShowAccount(false);
        setPurchase({ plan });
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
            setNotice('Activation de votre abonnement…');
            for (let i = 0; i < 15; i++) {
                if ((await refreshMe())?.is_pro) {
                    setNotice('Votre abonnement est actif : tous les outils SPREA sont débloqués.');
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
        config, session, me, requestReport, startSubscription, authedFetch,
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
                    onClose={() => setShowAccount(false)}
                    onDownload={downloadReport}
                    onSubscribe={async () => { setShowAccount(false); navigate('/tarifs'); }}
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
                        className="ml-3 px-3 py-1.5 rounded-lg bg-brass text-canvas font-semibold text-xs"
                    >
                        Obtenir le rapport
                    </button>
                </Toast>
            )}
            {purchase && (
                <PurchaseModal
                    plan={purchase.plan}
                    price={config?.plans?.[purchase.plan] ?? null}
                    onClose={() => setPurchase(null)}
                    onConfirm={async () => {
                        await subscribe(purchase.plan);
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
            className={`h-10 px-4 rounded-xl border border-line text-sm text-ink-soft hover:text-ink hover:border-brass/60 transition-colors flex items-center gap-2 ${className}`}
        >
            <UserIcon size={16} />
            <span className="hidden sm:inline">{session ? 'Mon compte' : 'Se connecter'}</span>
            {me?.is_pro && <span className="px-1.5 py-0.5 rounded bg-brass text-canvas text-[10px] font-semibold">PRO</span>}
        </button>
    );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);
    return (
        <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-panel border border-line rounded-2xl shadow-2xl shadow-black/50 w-full max-w-md max-h-[90vh] overflow-y-auto p-6 sm:p-8 relative" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
                <button onClick={onClose} className="absolute top-5 right-5 text-faint hover:text-ink" aria-label="Fermer"><X size={20} /></button>
                <h2 className="text-2xl text-ink mb-6 pr-8">{title}</h2>
                {children}
            </div>
        </div>
    );
}

function Toast({ children, onClose }: { children: ReactNode; onClose: () => void }) {
    return (
        <div role="status" className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[110] w-[min(560px,calc(100%-2rem))] bg-raised border border-line text-ink text-sm rounded-xl shadow-2xl shadow-black/50 px-5 py-4 flex items-center gap-3">
            <div className="flex-1 flex items-center flex-wrap gap-y-2">{children}</div>
            <button onClick={onClose} className="text-faint hover:text-ink" aria-label="Fermer"><X size={16} /></button>
        </div>
    );
}

function Checkbox({ checked, onChange, children, danger }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; danger?: boolean }) {
    return (
        <label className="flex items-start gap-3 text-sm text-ink-soft leading-relaxed cursor-pointer">
            <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className={`mt-1 h-4 w-4 shrink-0 ${danger ? 'accent-coral' : 'accent-brass'}`} />
            <span>{children}</span>
        </label>
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
            {reason && <p className="text-sm text-muted mb-5">{reason}</p>}
            {status === 'sent' ? (
                <div className="text-center py-4">
                    <Mail className="mx-auto text-brass mb-3" size={32} />
                    <p className="text-ink font-medium">Lien envoyé à {email}</p>
                    <p className="text-sm text-muted mt-2">Ouvrez l'email et cliquez sur le lien pour vous connecter. Pas de mot de passe à retenir.</p>
                </div>
            ) : (
                <form onSubmit={send} className="space-y-4">
                    <label className="block space-y-2">
                        <span className="text-sm text-ink-soft">Adresse email</span>
                        <input
                            type="email"
                            required
                            autoFocus
                            placeholder="vous@exemple.fr"
                            value={email}
                            onChange={e => setEmail(e.target.value)}
                            className="w-full h-12 px-4 rounded-xl bg-raised border border-line text-ink placeholder:text-faint outline-none focus:border-brass/70"
                        />
                    </label>
                    <Button type="submit" disabled={status === 'sending'} className="w-full">
                        {status === 'sending' && <Loader2 className="animate-spin" size={16} />}
                        Recevoir un lien de connexion
                    </Button>
                    {status === 'error' && <p className="text-sm text-coral">L'envoi a échoué, vérifiez l'adresse et réessayez.</p>}
                    <p className="text-xs text-faint leading-relaxed">
                        Votre email sert uniquement à vous connecter, à conserver vos rapports et à vous envoyer vos factures.{' '}
                        <a href="/confidentialite" target="_blank" rel="noopener" className="underline hover:text-ink">Politique de confidentialité</a>
                    </p>
                </form>
            )}
        </Modal>
    );
}

function AccountModal({ me, onClose, onDownload, onSubscribe, onPortal, onLogout, onDelete }: {
    me: Me | null;
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
            {!me ? <Loader2 className="animate-spin text-faint" /> : (
                <div className="space-y-6">
                    <p className="text-sm text-muted">{me.email}</p>

                    <div className="rounded-xl border border-line bg-raised p-5">
                        {me.is_pro ? (
                            <>
                                <p className="text-ink font-medium flex items-center gap-2"><Sparkles size={16} className="text-brass" /> Abonnement actif</p>
                                <p className="text-sm text-muted mt-1">Tous les outils inclus{periodEnd ? ` · renouvellement le ${periodEnd}` : ''}</p>
                            </>
                        ) : (
                            <>
                                <p className="text-ink font-medium">Aucun abonnement actif</p>
                                <p className="text-sm text-muted mt-1">
                                    Simulateur, carte de prospection, alertes, avis de valeur et rapports sont réservés aux abonnés. Satisfait ou remboursé pendant 14 jours.
                                </p>
                                <Button onClick={run('subscribe', onSubscribe)} className="mt-4 w-full">
                                    Choisir ma formule
                                </Button>
                            </>
                        )}
                        {me.has_billing_account && (
                            <Button variant="secondary" onClick={run('portal', onPortal)} className="mt-3 w-full h-10">
                                {busy === 'portal' && <Loader2 className="animate-spin" size={14} />}
                                Factures et abonnement
                            </Button>
                        )}
                    </div>

                    <div>
                        <p className="text-sm text-ink-soft font-medium mb-3">Mes rapports</p>
                        {me.reports.length === 0 ? (
                            <p className="text-sm text-faint">Aucun rapport pour le moment.</p>
                        ) : (
                            <ul className="space-y-2 max-h-60 overflow-y-auto">
                                {me.reports.map(r => (
                                    <li key={r.id} className="flex items-center justify-between gap-3 text-sm">
                                        <span className="truncate text-ink-soft">
                                            {r.address}
                                            <span className="block text-xs text-faint">{new Date(r.created_at).toLocaleDateString('fr-FR')}</span>
                                        </span>
                                        <button onClick={run(r.id, () => onDownload(r.id))} className="shrink-0 px-3 py-1.5 rounded-lg border border-line text-brass hover:border-brass/60 text-xs font-semibold flex items-center gap-1">
                                            {busy === r.id && <Loader2 className="animate-spin" size={12} />}
                                            PDF
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    <div className="flex items-center justify-between gap-4 border-t border-line pt-4">
                        <button onClick={run('logout', onLogout)} className="text-sm text-muted hover:text-ink flex items-center gap-2">
                            <LogOut size={14} /> Se déconnecter
                        </button>
                        <button onClick={onDelete} className="text-sm text-faint hover:text-coral flex items-center gap-2">
                            <Trash2 size={14} /> Supprimer mon compte
                        </button>
                    </div>
                </div>
            )}
        </Modal>
    );
}

const PLAN_NAMES: Record<Plan, string> = { solo_monthly: 'Solo · mensuel', solo_yearly: 'Solo · annuel' };

function PurchaseModal({ plan, price, onClose, onConfirm }: {
    plan: Plan;
    price: string | null | undefined;
    onClose: () => void;
    onConfirm: () => Promise<void>;
}) {
    const [accepted, setAccepted] = useState(false);
    const [busy, setBusy] = useState(false);
    const cgv = <a href="/cgv" target="_blank" rel="noopener" className="underline text-brass">conditions générales de vente</a>;

    return (
        <Modal title={`Abonnement ${PLAN_NAMES[plan]}`} onClose={onClose}>
            <div className="rounded-xl border border-line bg-raised p-5 mb-5">
                <p className="font-serif text-3xl text-ink">{price || '–'}<span className="font-sans text-xs text-faint ml-2">HT</span></p>
                <p className="text-sm text-muted mt-2">
                    Tous les outils SPREA, sans limite. Sans engagement, résiliable à tout moment depuis votre compte.
                    Satisfait ou remboursé pendant 14 jours. Facture avec TVA.
                </p>
            </div>
            <Checkbox checked={accepted} onChange={setAccepted}>
                J'accepte les {cgv} et je souscris pour les besoins de mon activité professionnelle.
            </Checkbox>
            <Button disabled={!accepted || busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }} className="mt-6 w-full">
                {busy && <Loader2 className="animate-spin" size={16} />}
                Continuer vers le paiement
            </Button>
            <p className="text-xs text-faint text-center mt-3">Paiement sécurisé par Stripe</p>
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
            <ul className="text-sm text-ink-soft leading-relaxed space-y-2 list-disc pl-5 mb-5">
                <li>Votre compte et votre adresse email sont supprimés.</li>
                <li>
                    {reportCount > 0
                        ? <><b className="text-ink">Vos {reportCount} rapport{reportCount > 1 ? 's' : ''}</b> ne pourront plus être téléchargés : enregistrez-les avant de continuer.</>
                        : 'Vos rapports sont supprimés.'}
                </li>
                {me?.is_pro && <li>Votre <b className="text-ink">abonnement est résilié immédiatement</b>, sans remboursement de la période en cours.</li>}
                <li>Les factures et une trace minimale de vos achats (date, montant, version des CGV acceptée) sont conservées pour nos obligations légales, sans vos simulations.</li>
            </ul>
            <Checkbox checked={understood} onChange={setUnderstood} danger>Je comprends que cette suppression est définitive.</Checkbox>
            <button
                disabled={!understood || busy}
                onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); } }}
                className="mt-6 w-full h-12 rounded-xl bg-coral text-canvas font-semibold text-sm hover:opacity-90 disabled:bg-raised disabled:text-faint disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
                {busy && <Loader2 className="animate-spin" size={16} />}
                Supprimer définitivement
            </button>
            <button onClick={onClose} className="mt-3 w-full text-sm text-muted hover:text-ink">Annuler</button>
        </Modal>
    );
}
