import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Phone, ShieldCheck } from 'lucide-react';
import { useSeo } from '../seo';
import { propertyInput, toProperty, toSimulation, type PropertyData, type Simulation } from '../model';
import { Link } from '../router';
import { Button, Card, DpeBadge, eur, eurRange, type DPEClass } from '../ui';

interface PageData {
    code: string;
    dpe_number: string;
    address: string;
    label: DPEClass | null;
    agency: { agency_name: string; agent_name?: string | null; phone?: string | null; email?: string | null };
    consent_text: string;
}

const LAW: Partial<Record<DPEClass, string>> = {
    G: "Depuis le 1er janvier 2025, un logement classé G ne peut plus être proposé à la location (nouveaux baux et renouvellements). Son loyer est gelé.",
    F: "À partir du 1er janvier 2028, un logement classé F ne pourra plus être proposé à la location. Son loyer est déjà gelé.",
    E: "À partir du 1er janvier 2034, un logement classé E ne pourra plus être proposé à la location.",
};

const fieldClass = 'w-full rounded-xl border border-line bg-raised px-3.5 h-11 text-ink outline-none focus:border-brass/70';

export default function OwnerPage({ code }: { code: string }) {
    // Personal page of a dwelling: never indexed
    useSeo({ title: 'Votre logement', noindex: true });
    const [page, setPage] = useState<PageData | null>(null);
    const [property, setProperty] = useState<PropertyData | null>(null);
    const [sim, setSim] = useState<Simulation | null>(null);
    const [works, setWorks] = useState<string[]>([]);
    const [notFound, setNotFound] = useState(false);
    const [form, setForm] = useState({ name: '', phone: '', email: '', message: '', consent: false, website: '' });
    const [sending, setSending] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Page, then the dwelling's DPE, local price and simulation of the recommended works
    // (the tools are for subscribers: the link code opens them for this page)
    const link = { 'X-Link-Code': code };
    useEffect(() => {
        (async () => {
            try {
                const res = await fetch(`/api/l/${code}`);
                if (!res.ok) { setNotFound(true); return; }
                const data: PageData = await res.json();
                setPage(data);
                document.title = `Votre logement · ${data.agency.agency_name}`;
                const dpe = await (await fetch(`/api/search-dpe/${encodeURIComponent(data.dpe_number)}`, { headers: link })).json();
                if (!dpe.results?.length) return;
                let p = toProperty(dpe.results[0]);
                if (p.inseeCode) {
                    const params = new URLSearchParams({ insee: p.inseeCode, building_type: p.buildingType || '', surface: String(p.surface || '') });
                    if (p.latitude != null && p.longitude != null) { params.set('lat', String(p.latitude)); params.set('lon', String(p.longitude)); }
                    const market = await fetch(`/api/market-price?${params}`, { headers: link }).then(r => (r.ok ? r.json() : null)).catch(() => null);
                    if (market?.price_per_m2) p = { ...p, pricePerM2: market.price_per_m2, priceSource: market.source };
                }
                setProperty(p);
                const selected = p.preselectedWorks?.length ? p.preselectedWorks : p.suggestedWorks || [];
                setWorks(selected);
                const simRes = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', ...link },
                    body: JSON.stringify({ property: propertyInput(p), works: selected, suggested_works: selected }),
                });
                if (simRes.ok) setSim(toSimulation(await simRes.json()));
            } catch {
                setNotFound(true);
            }
        })();
    }, [code]);

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        if (!form.consent) { setError("Cochez la case pour accepter d'être recontacté."); return; }
        if (!form.phone && !form.email) { setError('Indiquez un téléphone ou un email.'); return; }
        setSending(true);
        try {
            const res = await fetch(`/api/l/${code}/lead`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...form, phone: form.phone || null, email: form.email || null, message: form.message || null }),
            });
            if (res.status === 429) throw new Error('Trop de demandes envoyées : réessayez plus tard.');
            if (!res.ok) {
                const detail = await res.json().catch(() => ({}));
                const msg = Array.isArray(detail.detail) ? 'Vérifiez le téléphone et l\'email saisis.' : detail.detail;
                throw new Error(msg || "L'envoi a échoué.");
            }
            setSent(true);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setSending(false);
        }
    };

    if (notFound) {
        return (
            <div className="min-h-screen bg-canvas flex items-center justify-center px-4">
                <Card className="p-6 max-w-md text-center">
                    <p className="text-ink font-medium">Cette page n'existe pas ou n'est plus disponible.</p>
                    <Link to="/" className="mt-4 inline-block text-brass-light underline">Simuler la rénovation d'un logement</Link>
                </Card>
            </div>
        );
    }
    if (!page) {
        return <div className="min-h-screen bg-canvas flex items-center justify-center"><Loader2 className="animate-spin text-brass" /></div>;
    }

    // Official class of the DPE, as quoted in the letter
    const label = (page.label || property?.label || sim?.currentLabel) as DPEClass | undefined;
    const agency = page.agency;
    const workNames = sim?.detailedCosts.filter(c => works.includes(c.id)) || [];

    return (
        <div className="min-h-screen bg-canvas">
            <header className="border-b border-line/70">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 py-5 flex items-center justify-between gap-4">
                    <div>
                        <p className="font-serif text-2xl text-ink">{agency.agency_name}</p>
                        {agency.agent_name && <p className="text-sm text-muted">{agency.agent_name}</p>}
                    </div>
                    {agency.phone && (
                        <a href={`tel:${agency.phone.replace(/[^0-9+]/g, '')}`} className="flex items-center gap-2 text-sm text-brass-light hover:text-ink whitespace-nowrap">
                            <Phone size={16} />{agency.phone}
                        </a>
                    )}
                </div>
            </header>

            <main className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-6">
                <section>
                    <p className="text-sm text-brass">Votre logement</p>
                    <h1 className="mt-1 text-3xl sm:text-4xl text-ink">{page.address}</h1>
                    <div className="mt-5 flex items-center gap-4">
                        <DpeBadge label={label} size="lg" />
                        <p className="text-ink-soft">
                            D'après son diagnostic de performance énergétique (DPE n° {page.dpe_number}), ce logement est classé{' '}
                            <b className="text-ink">{label}</b>.
                        </p>
                    </div>
                    {label && LAW[label] && <p className="mt-4 rounded-xl border border-coral/40 bg-coral/10 p-4 text-sm text-ink-soft">{LAW[label]}</p>}
                </section>

                <Card className="p-5 sm:p-6">
                    <h2 className="text-xl text-ink">Ce que pourrait changer une rénovation</h2>
                    {!sim ? (
                        <p className="mt-3 text-sm text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" />Calcul en cours…</p>
                    ) : sim.cost === 0 ? (
                        <p className="mt-3 text-sm text-muted">Aucun travaux prioritaire n'a été identifié pour ce logement.</p>
                    ) : (
                        <>
                            <div className="mt-4 flex items-center gap-3">
                                <DpeBadge label={sim.currentLabel} />
                                <span className="text-faint">→</span>
                                <DpeBadge label={sim.newLabel} />
                                <span className="text-sm text-ink-soft">après {workNames.map(w => w.name.charAt(0).toLowerCase() + w.name.slice(1)).join(', ')}</span>
                            </div>
                            <dl className="mt-5 grid sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
                                <div className="flex justify-between gap-4 border-b border-line/70 pb-2"><dt className="text-ink-soft">Coût des travaux</dt><dd className="text-ink tabular-nums">{eurRange(sim.costLow, sim.costHigh)}</dd></div>
                                <div className="flex justify-between gap-4 border-b border-line/70 pb-2"><dt className="text-ink-soft">Aides estimées</dt><dd className="text-sage tabular-nums">− {eur(Math.round((sim.sub + sim.ceeEst) / 100) * 100)}</dd></div>
                                <div className="flex justify-between gap-4 border-b border-line/70 pb-2"><dt className="text-ink-soft">Reste à charge</dt><dd className="text-brass-light tabular-nums">{eurRange(sim.restLow, sim.restHigh)}</dd></div>
                                <div className="flex justify-between gap-4 border-b border-line/70 pb-2"><dt className="text-ink-soft">Économies sur la facture</dt><dd className="text-sage tabular-nums">{eur(Math.round(sim.savings / 10) * 10)} / an</dd></div>
                                {sim.gain > 0 && (
                                    <div className="flex justify-between gap-4 border-b border-line/70 pb-2 sm:col-span-2">
                                        <dt className="text-ink-soft">Valeur du bien après travaux</dt>
                                        <dd className="text-sage tabular-nums">+ {eurRange(sim.gainLow, sim.gainHigh)}</dd>
                                    </div>
                                )}
                            </dl>
                            <p className="mt-4 text-xs text-faint">
                                Estimation indicative à partir du DPE public, des coûts moyens de travaux, des aides en vigueur
                                (catégorie de revenus intermédiaire par défaut) et des ventes immobilières locales. Ce n'est ni un devis, ni un audit.
                            </p>
                        </>
                    )}
                </Card>

                <Card className="p-5 sm:p-6">
                    {sent ? (
                        <div className="text-center py-4">
                            <CheckCircle2 className="mx-auto text-sage" size={32} />
                            <p className="mt-3 text-ink font-medium">Votre demande a bien été transmise à {agency.agency_name}.</p>
                            <p className="mt-1 text-sm text-muted">Vous serez recontacté prochainement.</p>
                        </div>
                    ) : (
                        <form onSubmit={submit} className="space-y-4">
                            <div>
                                <h2 className="text-xl text-ink">Être rappelé par {agency.agent_name || agency.agency_name}</h2>
                                <p className="mt-1 text-sm text-muted">Pour une estimation de votre bien ou un plan de rénovation détaillé, sans engagement.</p>
                            </div>
                            <div className="grid sm:grid-cols-2 gap-3">
                                <input className={fieldClass} placeholder="Nom" required minLength={2} maxLength={80} autoComplete="name"
                                    value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} aria-label="Nom" />
                                <input className={fieldClass} placeholder="Téléphone" maxLength={25} autoComplete="tel" inputMode="tel"
                                    value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} aria-label="Téléphone" />
                                <input className={`${fieldClass} sm:col-span-2`} placeholder="Email (facultatif si téléphone)" type="email" maxLength={120} autoComplete="email"
                                    value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} aria-label="Email" />
                                <textarea className={`${fieldClass} sm:col-span-2 h-24 py-2.5`} placeholder="Message (facultatif) : vos disponibilités, votre projet…" maxLength={1000}
                                    value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} aria-label="Message" />
                                {/* Honeypot, hidden from people */}
                                <input className="hidden" tabIndex={-1} autoComplete="off" aria-hidden="true"
                                    value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} />
                            </div>
                            <label className="flex items-start gap-3 text-sm text-ink-soft">
                                <input type="checkbox" className="mt-1 h-4 w-4 accent-[#C9A45C]" checked={form.consent}
                                    onChange={e => setForm({ ...form, consent: e.target.checked })} />
                                <span>{page.consent_text}</span>
                            </label>
                            {error && <p className="text-sm text-coral">{error}</p>}
                            <Button type="submit" disabled={sending} className="w-full">
                                {sending && <Loader2 size={16} className="animate-spin" />}Être rappelé
                            </Button>
                            <p className="text-xs text-faint flex gap-2">
                                <ShieldCheck size={14} className="shrink-0 mt-0.5" />
                                <span>
                                    Vos coordonnées sont destinées uniquement à {agency.agency_name}, responsable de leur traitement, pour vous recontacter
                                    au sujet de ce logement. Elles sont conservées 3 ans au plus. Vous pouvez demander leur suppression à tout moment
                                    {agency.email ? ` à ${agency.email}` : ' auprès de l\'agence'}. L'adresse de ce courrier provient des DPE publiés par l'ADEME ;
                                    aucune autre donnée vous concernant n'est utilisée. <Link to="/confidentialite" className="underline">En savoir plus</Link>.
                                </span>
                            </p>
                        </form>
                    )}
                </Card>
            </main>
            <footer className="max-w-3xl mx-auto px-4 sm:px-6 py-8 text-xs text-faint">
                Simulation réalisée avec <Link to="/" className="underline">SPREA</Link>.
            </footer>
        </div>
    );
}
