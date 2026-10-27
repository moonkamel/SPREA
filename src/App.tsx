import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { AccountProvider, useAccount } from './account';
import { usePath } from './router';
import CgvPage from './pages/Cgv';
import ConfidentialitePage from './pages/Confidentialite';
import MentionsLegalesPage from './pages/MentionsLegales';
import PricingPage from './pages/Pricing';
import { NotFound } from './pages/site';
// Leaflet is only loaded on the map page
const ProspectionPage = lazy(() => import('./pages/Prospection'));
const OwnerPage = lazy(() => import('./pages/Owner'));
const ContactsPage = lazy(() => import('./pages/Contacts'));
const AlertsPage = lazy(() => import('./pages/Alerts'));
const ValuationDialog = lazy(() => import('./pages/ValuationDialog'));
const DossierDialog = lazy(() => import('./pages/Opportunities').then(m => ({ default: m.DossierDialog })));
const ObservatoirePage = lazy(() => import('./pages/Observatoire'));
const DemoPage = lazy(() => import('./pages/Demo'));
const TeamPage = lazy(() => import('./pages/Team'));
const JoinPage = lazy(() => import('./pages/Join'));
const CoproDocsPage = lazy(() => import('./pages/CoproDocs'));
const EstimationPage = lazy(() => import('./pages/Estimation'));
const CityPricePage = lazy(() => import('./pages/CityPrice'));
const CityPriceIndexPage = lazy(() => import('./pages/CityPrice').then(m => ({ default: m.CityPriceIndexPage })));
import Landing from './views/Landing';
import Home from './views/Home';
import Results from './views/Results';
import LoadingSequence, { SIMULATION_STEPS } from './views/LoadingSequence';
import Dashboard, { type Scenario, type Settings } from './views/Dashboard';
import { propertyInput, toProperty, toSimulation, type PropertyData, type RetrofitAction, type Simulation } from './model';
import type { DPEClass } from './ui';

export default function App() {
    return (
        <AccountProvider>
            <Pages />
        </AccountProvider>
    );
}

function Pages() {
    const rawPath = usePath();
    // "/tarifs/" -> "/tarifs"
    const path = rawPath.length > 1 ? rawPath.replace(/\/+$/, '') || '/' : rawPath;
    useEffect(() => {
        if (path === rawPath) return;
        window.history.replaceState(window.history.state, '', `${path}${window.location.search}${window.location.hash}`);
        window.dispatchEvent(new PopStateEvent('popstate'));
    }, [path, rawPath]);
    const pages: Record<string, JSX.Element> = {
        '/tarifs': <PricingPage />,
        '/cgv': <CgvPage />,
        '/mentions-legales': <MentionsLegalesPage />,
        '/confidentialite': <ConfidentialitePage />,
        '/prospection': <Suspense fallback={null}><ProspectionPage /></Suspense>,
        '/contacts': <Suspense fallback={null}><ContactsPage /></Suspense>,
        '/alertes': <Suspense fallback={null}><AlertsPage /></Suspense>,
        '/observatoire': <Suspense fallback={null}><ObservatoirePage /></Suspense>,
        '/demo': <Suspense fallback={null}><DemoPage /></Suspense>,
        '/equipe': <Suspense fallback={null}><TeamPage /></Suspense>,
        '/rejoindre': <Suspense fallback={null}><JoinPage /></Suspense>,
        '/documents-copro': <Suspense fallback={null}><CoproDocsPage /></Suspense>,
        '/estimation': <Suspense fallback={null}><EstimationPage /></Suspense>,
        '/prix-m2': <Suspense fallback={null}><CityPriceIndexPage /></Suspense>,
    };
    // Owner page reached from a letter's QR code: /l/<code>
    const ownerCode = path.match(/^\/l\/([A-Za-z0-9]{8})$/)?.[1];
    // Observatory of one department: /observatoire/<name>-<code> (unknown slug: 404 shown by the page)
    const department = path.match(/^\/observatoire\/([a-z0-9-]+)$/)?.[1];
    // Price per m2 of one commune: /prix-m2/<name>-<insee>
    const cityPrice = path.match(/^\/prix-m2\/([a-z0-9-]+-[0-9][0-9ab][0-9]{3})$/)?.[1];
    const page = ownerCode ? <Suspense fallback={null}><OwnerPage code={ownerCode} /></Suspense>
        : department ? <Suspense fallback={null}><ObservatoirePage slug={department} /></Suspense>
        : cityPrice ? <Suspense fallback={null}><CityPricePage slug={cityPrice} /></Suspense>
        : path === '/' ? null
        : pages[path] ?? <NotFound />;
    return (
        <>
            {page}
            {/* Kept mounted so the current simulation survives a visit to the other pages */}
            <div hidden={page !== null}><Gate /></div>
        </>
    );
}

const DEFAULT_SETTINGS: Settings = {
    incomeMode: 'level',
    incomeLevel: 'intermediaire',
    rfr: '',
    occupants: 2,
    isInvestor: false,
    monthlyRent: 800,
    purchasePrice: 150000,
    tmi: 30,
    nbEtages: 0,
    hasAscenseur: true,
    isUrbanDense: false,
    parkingCost: 35,
};

// Debounced server-side simulation; the previous result stays displayed meanwhile.
// `attempt` is bumped to retry after a failure.
type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

function useSimulation(input: object | null, attempt: number, setSim: (s: Simulation | null) => void, setBusy: (b: boolean) => void,
    setFailed: (f: boolean) => void, fetcher: Fetcher) {
    useEffect(() => {
        if (!input) return;
        const controller = new AbortController();
        setBusy(true);
        setFailed(false);
        const timer = setTimeout(async () => {
            try {
                const res = await fetcher('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(input),
                    signal: controller.signal,
                });
                if (!res.ok) throw new Error(`Simulation error: ${res.status}`);
                setSim(toSimulation(await res.json()));
                setBusy(false);
            } catch (err) {
                if ((err as Error).name !== 'AbortError') { console.error(err); setBusy(false); setFailed(true); }
            }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [input, attempt, setSim, setBusy, setFailed, fetcher]);
}

// The tools are for subscribers; visitors get the showcase
function Gate() {
    const { config, session, me } = useAccount();
    // Account still loading (or unreachable: show the showcase after a while)
    const [waited, setWaited] = useState(false);
    useEffect(() => {
        const timer = setTimeout(() => setWaited(true), 5000);
        return () => clearTimeout(timer);
    }, []);
    if (!waited && (!config || (session && !me))) {
        return <div className="min-h-screen flex items-center justify-center"><Loader2 className="animate-spin text-faint" /></div>;
    }
    return me?.is_pro ? <Simulator /> : <Home />;
}

function Simulator() {
    const { requestReport, config, me, authedFetch } = useAccount();
    const [view, setView] = useState<'landing' | 'results' | 'dashboard'>('landing');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<PropertyData[]>([]);
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
    const [scenario, setScenario] = useState<Scenario>('A');
    const [catalog, setCatalog] = useState<RetrofitAction[]>([]);
    const [actions, setActions] = useState<Record<Scenario, RetrofitAction[]>>({ A: [], B: [] });
    const [sims, setSims] = useState<Record<Scenario, Simulation | null>>({ A: null, B: null });
    const [busy, setBusy] = useState<Record<Scenario, boolean>>({ A: false, B: false });
    const [failed, setFailed] = useState<Record<Scenario, boolean>>({ A: false, B: false });
    const [attempts, setAttempts] = useState<Record<Scenario, number>>({ A: 0, B: 0 });
    const [downloading, setDownloading] = useState(false);
    const [showValuation, setShowValuation] = useState(false);
    const [showDossier, setShowDossier] = useState(false);
    // Analysis screen, from the search until the first simulation is back
    const [analyzing, setAnalyzing] = useState(false);
    useEffect(() => { if (error) setAnalyzing(false); }, [error]);

    useEffect(() => {
        // Cancelled when the page is left; one retry on a network failure
        const controller = new AbortController();
        const load = (attempt: number): Promise<void> => fetch('/api/works', { signal: controller.signal })
            .then(res => res.json())
            .then(data => setCatalog((data.works || []).map((w: any) => ({ id: w.id, name: w.name, description: w.description, active: false }))))
            .catch(err => {
                if (controller.signal.aborted) return;
                if (attempt === 0) return new Promise<void>(resolve => setTimeout(resolve, 1500)).then(() => load(1));
                console.error('Works catalog error:', err);
            });
        load(0);
        return () => controller.abort();
    }, []);

    // Opened from the prospection map: /?dpe=NUMBER
    const path = usePath();
    useEffect(() => {
        const dpe = new URLSearchParams(window.location.search).get('dpe');
        if (path !== '/' || !dpe || !catalog.length) return;
        window.history.replaceState({}, '', '/');
        search(`/api/search-dpe/${encodeURIComponent(dpe)}`, 'Ce DPE est introuvable.');
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [path, catalog.length]);

    const goHome = () => { setView('landing'); setError(null); setAnalyzing(false); window.scrollTo(0, 0); };

    const search = async (url: string, notFound: string) => {
        setLoading(true);
        setAnalyzing(true);
        setError(null);
        try {
            const res = await authedFetch(url);
            if (res.status === 429) throw new Error('Trop de recherches en peu de temps : patientez une minute puis réessayez.');
            if (!res.ok) throw new Error();
            const data = await res.json();
            if (data.results?.length) {
                const found = data.results.map(toProperty);
                if (found.length === 1) selectProperty(found[0]);
                else { setResults(found); setView('results'); window.scrollTo(0, 0); }
            } else {
                setError(data.error ? "Le service de l'ADEME ne répond pas pour le moment. Réessayez dans quelques secondes." : notFound);
            }
        } catch (e) {
            setError((e as Error).message || 'La recherche a échoué. Vérifiez votre connexion et réessayez.');
        } finally {
            setLoading(false);
        }
    };

    const selectProperty = (p: PropertyData) => {
        const suggested = new Set(p.suggestedWorks || []);
        const preselected = new Set(p.preselectedWorks || []);
        setProperty(p);
        setSettings({ ...DEFAULT_SETTINGS, purchasePrice: Math.round(p.surface * 4200 / 1000) * 1000 });
        setScenario('A');
        setSims({ A: null, B: null });
        setActions({
            A: catalog.map(a => ({ ...a, suggested: suggested.has(a.id), active: preselected.has(a.id) })),
            B: catalog.map(a => ({ ...a, suggested: suggested.has(a.id), active: false })),
        });
        setView('dashboard');
        window.scrollTo(0, 0);
        loadMarketPrice(p);
    };

    // Local price per m2 from DVF sales (green value, default purchase price)
    const loadMarketPrice = async (p: PropertyData) => {
        const done = (patch: Partial<PropertyData> = {}) => setProperty(current =>
            current && current.ademe_dpe_number === p.ademe_dpe_number ? { ...current, ...patch, priceLookupDone: true } : current);
        if (!p.inseeCode) return done();
        const params = new URLSearchParams({ insee: p.inseeCode, building_type: p.buildingType || '', surface: String(p.surface || '') });
        if (p.latitude != null && p.longitude != null) {
            params.set('lat', String(p.latitude));
            params.set('lon', String(p.longitude));
        }
        try {
            const res = await authedFetch(`/api/market-price?${params}`);
            const market = res.ok ? await res.json() : null;
            if (!market?.price_per_m2) return done();
            const defaultPrice = Math.round(p.surface * 4200 / 1000) * 1000;
            done({ pricePerM2: market.price_per_m2, priceSource: market.source });
            setSettings(s => s.purchasePrice === defaultPrice
                ? { ...s, purchasePrice: Math.round(p.surface * market.price_per_m2 / 1000) * 1000 }
                : s);
        } catch {
            done(); // Default price per m2 stays in place
        }
    };

    const toggle = (id: string) =>
        setActions(prev => ({ ...prev, [scenario]: prev[scenario].map(a => (a.id === id ? { ...a, active: !a.active } : a)) }));

    const updateSettings = (patch: Partial<Settings>) => setSettings(s => ({ ...s, ...patch }));

    const buildInput = useCallback((list: RetrofitAction[]) => {
        if (!property) return null;
        const s = settings;
        const useRfr = s.incomeMode === 'rfr' && s.rfr !== '';
        return {
            property: propertyInput(property),
            works: list.filter(a => a.active).map(a => a.id),
            suggested_works: list.filter(a => a.suggested).map(a => a.id),
            income_level: s.incomeLevel,
            ...(useRfr ? { rfr: Number(s.rfr), occupants: Math.max(1, Number(s.occupants) || 1) } : {}),
            nb_etages: Number(s.nbEtages) || 0,
            has_ascenseur: s.hasAscenseur,
            is_urban_dense: s.isUrbanDense,
            parking_cost: Number(s.parkingCost) || 0,
            is_investor: s.isInvestor,
            monthly_rent: Number(s.monthlyRent) || 0,
            purchase_price: Number(s.purchasePrice) || 0,
            tmi: s.tmi,
        };
    }, [property, settings]);

    const inputA = useMemo(() => buildInput(actions.A), [buildInput, actions.A]);
    const inputB = useMemo(() => buildInput(actions.B), [buildInput, actions.B]);
    const setSimA = useCallback((s: Simulation | null) => setSims(p => ({ ...p, A: s })), []);
    const setSimB = useCallback((s: Simulation | null) => setSims(p => ({ ...p, B: s })), []);
    const setBusyA = useCallback((b: boolean) => setBusy(p => ({ ...p, A: b })), []);
    const setBusyB = useCallback((b: boolean) => setBusy(p => ({ ...p, B: b })), []);
    const setFailedA = useCallback((f: boolean) => setFailed(p => ({ ...p, A: f })), []);
    const setFailedB = useCallback((f: boolean) => setFailed(p => ({ ...p, B: f })), []);
    useSimulation(inputA, attempts.A, setSimA, setBusyA, setFailedA, authedFetch);
    useSimulation(inputB, attempts.B, setSimB, setBusyB, setFailedB, authedFetch);

    const reportMeta = () => property && ({
        address: property.address || 'Adresse inconnue',
        year: property.year || null,
        ademe_dpe_number: property.ademe_dpe_number || null,
        building_type: property.buildingType || null,
        construction_period: property.constructionPeriod || null,
        dpe_date: property.dpeDate || null,
        city: property.city || null,
        postcode: property.postcode || null,
        details: property.details || null,
        insee_code: property.inseeCode || null,
        latitude: property.latitude ?? null,
        longitude: property.longitude ?? null,
    });

    const downloadReport = async () => {
        const simulation = scenario === 'A' ? inputA : inputB;
        if (!property || !simulation) return;
        setDownloading(true);
        try {
            await requestReport({
                meta: reportMeta()!,
                simulation,
            });
        } finally {
            setDownloading(false);
        }
    };

    // Data ready: list of diagnostics, or the first simulation done (or failed)
    const analysisDone = !loading && (view === 'results' || (view === 'dashboard' && (!!sims.A || !busy.A)));
    const analysis = analyzing && (
        <LoadingSequence
            steps={SIMULATION_STEPS}
            title="Analyse du logement"
            subtitle={view === 'dashboard' ? property?.address : undefined}
            sources="ADEME, DVF (DGFiP), Anah, barèmes officiels 2026"
            done={analysisDone}
            onFinished={() => setAnalyzing(false)}
        />
    );

    // Same place in the tree whatever the view, so the sequence runs on across them
    return <>{analysis}{page()}</>;

    function page() {
        if (view === 'results') {
            return <Results results={results} onSelect={p => { setAnalyzing(true); selectProperty(p); }} onBack={goHome} />;
        }

        if (view === 'dashboard' && property) {
            const currentInput = scenario === 'A' ? inputA : inputB;
            return (
                <>
                {showValuation && currentInput && (
                    <Suspense fallback={null}>
                        <ValuationDialog meta={reportMeta()!} simulation={currentInput} onClose={() => setShowValuation(false)} />
                    </Suspense>
                )}
                {showDossier && currentInput && (
                    <Suspense fallback={null}>
                        <DossierDialog audience="acheteur"
                            preview={{
                                address: property.address, kind: (property.buildingType || 'logement').replace(/^./, c => c.toUpperCase()), surface: property.surface || 0,
                                label: (sims[scenario]?.currentLabel || property.label) as DPEClass, new_label: (sims[scenario]?.newLabel || property.label) as DPEClass,
                                works_names: actions[scenario].filter(a => a.active).map(a => a.name),
                            }}
                            request={{ url: '/api/opportunities/dossier/simulation', body: { meta: reportMeta(), simulation: currentInput } }}
                            onClose={() => setShowDossier(false)} />
                    </Suspense>
                )}
                <Dashboard
                    property={property}
                    scenario={scenario}
                    onScenario={setScenario}
                    actions={actions[scenario]}
                    onToggle={toggle}
                    sims={sims}
                    worksCount={{ A: actions.A.filter(a => a.active).length, B: actions.B.filter(a => a.active).length }}
                    updating={busy[scenario]}
                    failed={failed[scenario] && !busy[scenario]}
                    onRetry={() => setAttempts(p => ({ ...p, [scenario]: p[scenario] + 1 }))}
                    settings={settings}
                    onSettings={updateSettings}
                    report={{
                        // Reports need accounts and payments to be configured on the server
                        available: !!config?.auth_enabled && !!config?.billing_enabled,
                        price: config?.report_price ?? null,
                        included: !!me?.is_pro,
                        downloading,
                        onDownload: downloadReport,
                    }}
                    valuation={me?.is_pro && property.inseeCode ? () => setShowValuation(true) : undefined}
                    buyerDossier={me?.is_pro && property.inseeCode ? () => setShowDossier(true) : undefined}
                    onBack={goHome}
                />
                </>
            );
        }

        return (
            <Landing
                loading={loading}
                error={error}
                onSearchAddress={address => search(`/api/search-address?q=${encodeURIComponent(address)}`, "Aucun DPE n'a été trouvé à cette adresse. Essayez avec le numéro du DPE, indiqué en haut du diagnostic.")}
                onSearchDpe={n => search(`/api/search-dpe/${encodeURIComponent(n)}`, 'Aucun DPE ne correspond à ce numéro. Vérifiez les 13 caractères.')}
            />
        );
    }
}
