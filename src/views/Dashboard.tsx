import { useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowRight, Check, ChevronDown, CheckCircle2, FileText, Loader2, Info, Scale } from 'lucide-react';
import { Button, Card, DpeBadge, DpeScale, Help, Label, NumberField, Row, Segmented, Step, Switch, eur, eurRange, num } from '../ui';
import { SiteFooter, SiteHeader } from '../pages/site';
import RgeCompanies from './RgeCompanies';
import { INCOME_LEVELS, capitalize, formatDate, isHouse, type IncomeLevel, type PropertyData, type RetrofitAction, type Simulation } from '../model';

export interface Settings {
    incomeMode: 'level' | 'rfr';
    incomeLevel: IncomeLevel;
    rfr: number | '';
    occupants: number | '';
    isInvestor: boolean;
    monthlyRent: number | '';
    purchasePrice: number | '';
    tmi: number;
    nbEtages: number | '';
    hasAscenseur: boolean;
    isUrbanDense: boolean;
    parkingCost: number | '';
}

export type Scenario = 'A' | 'B';

interface Props {
    property: PropertyData;
    scenario: Scenario;
    onScenario: (s: Scenario) => void;
    actions: RetrofitAction[];
    onToggle: (id: string) => void;
    sims: Record<Scenario, Simulation | null>;
    worksCount: Record<Scenario, number>;
    updating: boolean;
    settings: Settings;
    onSettings: (patch: Partial<Settings>) => void;
    report: { available: boolean; price: string | null; included: boolean; downloading: boolean; onDownload: () => void };
    // Pro: avis de valeur avant / après rénovation
    valuation?: () => void;
    onBack: () => void;
}

const LOSS_ELEMENTS = [
    { id: 'roof', name: 'Toiture' },
    { id: 'walls', name: 'Murs' },
    { id: 'windows', name: 'Fenêtres' },
    { id: 'floor', name: 'Plancher bas' },
    { id: 'air', name: "Renouvellement d'air" },
    { id: 'bridges', name: 'Ponts thermiques' },
];

function climateStatus(ban: Date | null) {
    if (!ban) return null;
    const year = ban.getFullYear();
    return ban <= new Date() ? `Location interdite depuis ${year}` : `Location interdite à partir de ${year}`;
}

// --- Summary (sticky on desktop) ---

function Summary({ sim, property, report, updating, scenarioName, valuation }: {
    sim: Simulation | null;
    property: PropertyData;
    report: Props['report'];
    updating: boolean;
    scenarioName: string;
    valuation?: () => void;
}) {
    const aids = (sim?.sub || 0) + (sim?.ceeEst || 0);
    const noWorks = sim && sim.cost === 0;
    return (
        <Card className="p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
                <h2 className="text-xl text-ink">Votre projet</h2>
                <span className="text-xs text-faint flex items-center gap-1.5">
                    {updating && <Loader2 size={12} className="animate-spin" />}{scenarioName}
                </span>
            </div>

            <div className="mt-5 flex items-center gap-3">
                <DpeBadge label={sim?.currentLabel || property.label} size="lg" />
                <ArrowRight className="text-faint" />
                <DpeBadge label={sim?.newLabel} size="lg" />
                <div className="ml-1 text-sm">
                    <p className="text-ink">{sim && sim.gainClasses > 0 ? `+${sim.gainClasses} classe${sim.gainClasses > 1 ? 's' : ''}` : 'Pas de changement'}</p>
                    <p className="text-faint">{sim ? `${num(sim.newCep)} kWh/m²/an` : '…'}</p>
                </div>
            </div>

            {noWorks ? (
                <p className="mt-6 text-sm text-muted">Sélectionnez des travaux à l'étape 2 pour estimer leur coût et leurs effets.</p>
            ) : (
                <>
                    <div className="mt-5 divide-y divide-line/70">
                        <Row label="Coût des travaux" help="cost" value={sim ? eurRange(sim.costLow, sim.costHigh) : '…'} />
                        <Row label="Aides estimées" help="mpr" value={aids > 0 ? `− ${eur(aids)}` : eur(0)} tone={aids > 0 ? 'positive' : 'muted'} />
                    </div>
                    <div className="mt-3 rounded-xl bg-raised p-4">
                        <p className="text-sm text-ink-soft flex items-center gap-1.5">Reste à charge <Help topic="rest" /></p>
                        <p className="font-serif text-4xl text-brass-light mt-1 tabular-nums">≈ {eur(Math.round((sim?.rest || 0) / 100) * 100)}</p>
                        {sim && <p className="text-xs text-muted mt-1 tabular-nums">entre {eurRange(sim.restLow, sim.restHigh)}</p>}
                        {!!sim?.ecoPTZAmount && (
                            <p className="text-xs text-muted mt-2 flex items-center gap-1.5">
                                Finançable à 0 % jusqu'à {eur(sim.ecoPTZAmount)} <Help topic="ecoPtz" />
                            </p>
                        )}
                    </div>
                    <div className="mt-3 divide-y divide-line/70">
                        <Row label="Économies sur la facture" help="savings" value={sim && sim.savings > 0 ? `${eur(sim.savings)} / an` : '–'} tone={sim && sim.savings > 0 ? 'positive' : 'muted'} />
                        <Row label="Retour sur investissement" help="payback" value={sim?.roi != null && sim.roi >= 0 ? (sim.roi < 1 ? "moins d'un an" : `${Math.round(sim.roi)} ans`) : '–'} />
                        {!!sim?.gain && <Row label="Valeur verte du bien" help="greenValue" value={`+ ${eur(Math.round(sim.gain / 500) * 500)}`} tone="positive" />}
                        {!!sim?.gain && (
                            <div className="pb-2 text-xs text-faint space-y-1">
                                <p className="tabular-nums">Entre {eur(Math.round(sim.gainLow / 500) * 500)} et {eur(Math.round(sim.gainHigh / 500) * 500)}.</p>
                                <p>
                                    {property.priceSource
                                        ? `Prix local : ${num(property.pricePerM2)} €/m², ${property.priceSource}.`
                                        : property.priceLookupDone
                                            ? 'Prix local : 4 500 €/m² par défaut, pas assez de ventes connues à proximité.'
                                            : 'Recherche des prix de vente locaux (DVF)…'}
                                </p>
                                {sim.greenValueBasis && <p>Écart entre classes : {sim.greenValueBasis}.</p>}
                            </div>
                        )}
                    </div>
                </>
            )}

            {sim?.banDate && (
                <div className="mt-4 text-sm flex items-start gap-2">
                    {sim.newBanDate
                        ? <AlertTriangle size={16} className="text-coral mt-0.5 shrink-0" />
                        : <CheckCircle2 size={16} className="text-sage mt-0.5 shrink-0" />}
                    <span className="text-ink-soft">
                        Après travaux : {sim.newRentalStatus.toLowerCase()}.
                    </span>
                    <Help topic="climateLaw" />
                </div>
            )}

            <div className="mt-6 border-t border-line pt-5">
                <Button onClick={report.onDownload} disabled={!report.available || report.downloading || !sim || !!noWorks} className="w-full">
                    {report.downloading ? <Loader2 className="animate-spin" size={18} /> : <FileText size={18} />}
                    Télécharger le rapport PDF
                </Button>
                <p className="mt-2 text-xs text-faint text-center flex items-center justify-center gap-1.5">
                    {!report.available
                        ? 'Le rapport PDF sera disponible très prochainement.'
                        : report.included ? 'Inclus dans votre abonnement' : report.price ? `${report.price} TTC · paiement sécurisé` : 'Paiement sécurisé'}
                    <Help topic="report" />
                </p>
                {valuation && (
                    <Button variant="secondary" onClick={valuation} disabled={!sim} className="w-full mt-3">
                        <Scale size={18} />Avis de valeur avant / après
                    </Button>
                )}
            </div>
        </Card>
    );
}

// --- Main view ---

export default function Dashboard(props: Props) {
    const { property, scenario, onScenario, actions, onToggle, sims, worksCount, updating, settings, onSettings, report, onBack } = props;
    const sim = sims[scenario];
    const [showAdvanced, setShowAdvanced] = useState(false);
    const house = isHouse(property.buildingType);
    const costs = new Map((sim?.detailedCosts || []).map(c => [c.id, c.cost]));
    const visibleActions = actions.filter(a => a.id !== 'roof' || house);
    const recomputed = sim && property.label && sim.currentLabel !== property.label;
    const shares = property.lossShares;
    const maxShare = shares ? Math.max(...Object.values(shares)) : 1;
    const compare = sims.A && sims.B && worksCount.A > 0 && worksCount.B > 0;
    const scenarioName = scenario === 'A' ? 'Scénario recommandé' : 'Scénario personnalisé';

    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader onHome={onBack} />

            <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8">
                {/* Property header */}
                <button onClick={onBack} className="flex items-center gap-2 text-sm text-muted hover:text-ink mb-5">
                    <ArrowLeft size={16} /> Nouvelle recherche
                </button>
                <div className="mb-8">
                    <h1 className="text-3xl sm:text-4xl text-ink">{property.address}</h1>
                    {(property.postcode || property.city) && !property.address.includes(property.postcode || '#') && (
                        <p className="mt-1 font-serif text-lg text-ink-soft">{[property.postcode, property.city].filter(Boolean).join(' ')}</p>
                    )}
                    <p className="mt-2 text-muted">
                        {[capitalize(property.buildingType), property.surface ? `${property.surface} m²` : null, property.constructionPeriod || (property.year ? `construit en ${property.year}` : null)].filter(Boolean).join(' · ')}
                    </p>
                    <p className="mt-1 text-xs text-faint">
                        {property.dpeDate ? `DPE du ${formatDate(property.dpeDate)}` : 'DPE'}{property.ademe_dpe_number ? ` · n° ${property.ademe_dpe_number}` : ''}
                    </p>
                </div>

                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
                    {/* Summary first on mobile, sticky column on desktop */}
                    <aside className="lg:order-2 lg:sticky lg:top-24">
                        <Summary sim={sim} property={property} report={report} updating={updating} scenarioName={scenarioName} valuation={props.valuation} />
                    </aside>

                    <div className="lg:order-1 space-y-6 min-w-0">
                        {/* 1. Today */}
                        <Step n={1} title="Votre logement aujourd'hui" subtitle="Ce que dit le diagnostic de performance énergétique." help="dpe">
                            <div className="grid gap-6 md:grid-cols-2">
                                <div className="space-y-4">
                                    <div className="flex items-center gap-4">
                                        <DpeBadge label={sim?.currentLabel || property.label} size="lg" />
                                        <div>
                                            <p className="text-ink font-medium flex items-center gap-1.5">Étiquette énergie <Help topic="label" /></p>
                                            {recomputed ? (
                                                <p className="text-sm text-muted flex items-center gap-1.5">
                                                    DPE officiel : {property.label} · recalculée : {sim?.currentLabel} <Help topic="labelRecomputed" />
                                                </p>
                                            ) : (
                                                <p className="text-sm text-muted">Classe {property.label} sur une échelle de A à G</p>
                                            )}
                                        </div>
                                    </div>
                                    <div className="divide-y divide-line/70">
                                        <Row label="Consommation" help="consumption" value={`${num(property.initialCep)} kWh/m²/an`} />
                                        <Row label="Émissions de CO₂" value={`${num(sim?.initialGes ?? property.gesValue)} kg/m²/an`} />
                                        {property.heatingType && <Row label="Chauffage" value={capitalize(property.heatingType)} />}
                                        <Row label="Facture d'énergie estimée" help="bill" value={sim ? `${eur(sim.billBefore)} / an` : '…'} />
                                    </div>
                                    {sim?.banDate ? (
                                        <div className="rounded-xl border border-coral/40 bg-coral/10 p-4 flex gap-3">
                                            <AlertTriangle size={18} className="text-coral shrink-0 mt-0.5" />
                                            <div className="text-sm">
                                                <p className="text-ink font-medium flex items-center gap-1.5">{climateStatus(sim.banDate)} <Help topic="climateLaw" /></p>
                                                <p className="text-ink-soft mt-1">Loi Climat et Résilience : les logements classés {sim.currentLabel} ne peuvent plus être proposés à la location à cette date.</p>
                                            </div>
                                        </div>
                                    ) : sim && (
                                        <div className="rounded-xl border border-sage/30 bg-sage/10 p-4 flex gap-3 text-sm">
                                            <CheckCircle2 size={18} className="text-sage shrink-0 mt-0.5" />
                                            <p className="text-ink-soft">Aucune interdiction de location prévue pour cette classe. <Help topic="climateLaw" /></p>
                                        </div>
                                    )}
                                </div>

                                {shares && (
                                    <div>
                                        <p className="text-ink font-medium flex items-center gap-1.5 mb-4">Où part la chaleur ? <Help topic="heatLoss" /></p>
                                        <ul className="space-y-3">
                                            {LOSS_ELEMENTS.filter(e => (shares[e.id] || 0) > 0.005).sort((a, b) => (shares[b.id] || 0) - (shares[a.id] || 0)).map(e => {
                                                const v = shares[e.id] || 0;
                                                return (
                                                    <li key={e.id}>
                                                        <div className="flex justify-between text-sm mb-1">
                                                            <span className="text-ink-soft">{e.name}</span>
                                                            <span className="text-muted tabular-nums">{Math.round(v * 100)} %</span>
                                                        </div>
                                                        <div className="h-2 rounded-full bg-raised overflow-hidden">
                                                            <div className="h-full rounded-full bg-brass" style={{ width: `${(v / maxShare) * 100}%`, opacity: 0.45 + 0.55 * (v / maxShare) }} />
                                                        </div>
                                                    </li>
                                                );
                                            })}
                                        </ul>
                                        <p className="mt-3 text-xs text-faint">Estimation selon le type de logement, l'époque de construction et l'isolation déclarée.</p>
                                    </div>
                                )}
                            </div>
                        </Step>

                        {/* 2. Works */}
                        <Step n={2} title="Choisissez les travaux" subtitle="Cochez les travaux envisagés : tout se recalcule instantanément." help="works">
                            <div className="mb-5 max-w-md">
                                <Segmented
                                    ariaLabel="Scénario"
                                    value={scenario}
                                    onChange={onScenario}
                                    options={[
                                        { value: 'A', label: 'Recommandé', hint: 'Notre sélection' },
                                        { value: 'B', label: 'Personnalisé', hint: 'À composer vous-même' },
                                    ]}
                                />
                                <p className="mt-2 text-xs text-faint flex items-center gap-1.5">Comparez deux bouquets de travaux <Help topic="scenarios" /></p>
                            </div>

                            {scenario === 'A' && worksCount.A === 0 && (
                                <p className="mb-4 text-sm text-muted flex items-center gap-2"><Info size={16} className="text-brass" />Ce logement est déjà performant : aucun travaux prioritaire. Vous pouvez en ajouter ci-dessous.</p>
                            )}

                            <ul className="grid gap-3 sm:grid-cols-2">
                                {visibleActions.map(a => (
                                    <li key={a.id}>
                                        <button type="button" role="checkbox" aria-checked={a.active} onClick={() => onToggle(a.id)}
                                            className={`w-full h-full text-left rounded-xl border p-4 transition-colors flex gap-3 ${a.active ? 'border-brass/70 bg-brass/[0.07]' : 'border-line hover:border-faint'}`}>
                                            <span className={`mt-0.5 h-5 w-5 shrink-0 rounded-md border flex items-center justify-center ${a.active ? 'bg-brass border-brass text-canvas' : 'border-faint'}`}>
                                                {a.active && <Check size={14} strokeWidth={3} />}
                                            </span>
                                            <span className="flex-1 min-w-0">
                                                <span className="flex flex-wrap items-center gap-2">
                                                    <span className="text-ink font-medium">{a.name}</span>
                                                    {a.suggested && <span className="text-[11px] px-2 py-0.5 rounded-full border border-brass/50 text-brass">Recommandé</span>}
                                                </span>
                                                <span className="block text-sm text-muted mt-1 leading-snug">{a.description}</span>
                                                {a.active && costs.has(a.id) && <span className="block text-sm text-ink-soft mt-2 tabular-nums">≈ {eur(costs.get(a.id))}</span>}
                                            </span>
                                        </button>
                                    </li>
                                ))}
                            </ul>

                            {sim?.hasITI && <p className="mt-4 text-sm text-muted">L'isolation des murs par l'intérieur réduit la surface habitable d'environ 1,5 %.</p>}
                            {sim && sim.cost > 0 && <p className="mt-2 text-sm text-faint">Durée indicative du chantier : {sim.durationDays} jour{sim.durationDays > 1 ? 's' : ''} ouvrés.</p>}

                            {sim && (
                                <div className="mt-8 grid gap-6 md:grid-cols-2 items-center">
                                    <DpeScale thresholds={sim.thresholds} current={sim.currentLabel} target={sim.newLabel} />
                                    <div className="text-sm text-ink-soft space-y-2">
                                        <p>
                                            Avec ces travaux, le logement passerait de la classe <b className="text-ink">{sim.currentLabel}</b> à la classe <b className="text-ink">{sim.newLabel}</b>,
                                            pour une consommation de <b className="text-ink">{num(sim.newCep)} kWh/m²/an</b>.
                                        </p>
                                        <p>Facture d'énergie estimée : <b className="text-ink">{eur(sim.billBefore)}</b> → <b className="text-sage">{eur(sim.billAfter)}</b> par an.</p>
                                    </div>
                                </div>
                            )}

                            {compare && (
                                <div className="mt-8 overflow-x-auto">
                                    <p className="text-ink font-medium mb-3">Comparaison des deux scénarios</p>
                                    <table className="w-full text-sm min-w-[420px]">
                                        <thead>
                                            <tr className="text-faint text-left">
                                                <th className="font-normal py-2"></th>
                                                <th className="font-normal py-2">Recommandé</th>
                                                <th className="font-normal py-2">Personnalisé</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-line/70 tabular-nums">
                                            {[
                                                ['Classe après travaux', (s: Simulation) => <DpeBadge label={s.newLabel} size="sm" />],
                                                ['Coût des travaux', (s: Simulation) => eurRange(s.costLow, s.costHigh)],
                                                ['Reste à charge', (s: Simulation) => eurRange(s.restLow, s.restHigh)],
                                                ['Économies / an', (s: Simulation) => eur(s.savings)],
                                            ].map(([label, f]) => (
                                                <tr key={label as string}>
                                                    <td className="py-2.5 text-ink-soft">{label as string}</td>
                                                    <td className="py-2.5 text-ink">{(f as (s: Simulation) => React.ReactNode)(sims.A!)}</td>
                                                    <td className="py-2.5 text-ink">{(f as (s: Simulation) => React.ReactNode)(sims.B!)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Step>

                        {/* 3. Situation */}
                        <Step n={3} title="Votre situation" subtitle="Pour calculer les aides auxquelles vous avez droit.">
                            <div className="space-y-7">
                                <div className="space-y-3">
                                    <Label help="profile">Vous êtes</Label>
                                    <Segmented
                                        ariaLabel="Profil"
                                        value={settings.isInvestor ? 'investor' : 'owner'}
                                        onChange={v => onSettings({ isInvestor: v === 'investor' })}
                                        options={[
                                            { value: 'owner', label: 'Propriétaire occupant', hint: "J'habite le logement" },
                                            { value: 'investor', label: 'Investisseur bailleur', hint: 'Je le loue' },
                                        ]}
                                    />
                                </div>

                                <div className="space-y-3">
                                    <Label help="income">Revenus du foyer</Label>
                                    {settings.incomeMode === 'level' ? (
                                        <>
                                            <Segmented
                                                ariaLabel="Catégorie de revenus"
                                                value={settings.incomeLevel}
                                                onChange={v => onSettings({ incomeLevel: v })}
                                                options={INCOME_LEVELS.map(l => ({ value: l.value, label: l.label }))}
                                            />
                                            <button onClick={() => onSettings({ incomeMode: 'rfr' })} className="text-sm text-brass hover:text-brass-light">
                                                Je ne connais pas ma catégorie : la calculer avec mon revenu fiscal
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <div className="grid gap-4 sm:grid-cols-2">
                                                <label className="space-y-2 block">
                                                    <Label help="rfr">Revenu fiscal de référence</Label>
                                                    <NumberField ariaLabel="Revenu fiscal de référence" value={settings.rfr} onChange={v => onSettings({ rfr: v })} suffix="€ / an" step={1000} />
                                                </label>
                                                <label className="space-y-2 block">
                                                    <Label>Personnes dans le foyer</Label>
                                                    <NumberField ariaLabel="Personnes dans le foyer" value={settings.occupants} onChange={v => onSettings({ occupants: v === '' ? '' : Math.max(1, Math.round(v)) })} min={1} />
                                                </label>
                                            </div>
                                            <p className="text-sm text-ink-soft">
                                                {settings.rfr !== '' && sim ? <>Catégorie MaPrimeRénov' : <b className="text-brass-light">{sim.incomeProfile}</b></> : 'Indiquez votre revenu fiscal pour connaître votre catégorie.'}
                                            </p>
                                            <button onClick={() => onSettings({ incomeMode: 'level' })} className="text-sm text-brass hover:text-brass-light">Choisir ma catégorie directement</button>
                                        </>
                                    )}
                                </div>

                                {settings.isInvestor && (
                                    <div className="grid gap-4 sm:grid-cols-2">
                                        <label className="space-y-2 block">
                                            <Label>Prix d'achat du bien</Label>
                                            <NumberField ariaLabel="Prix d'achat" value={settings.purchasePrice} onChange={v => onSettings({ purchasePrice: v })} suffix="€" step={5000} />
                                        </label>
                                        <label className="space-y-2 block">
                                            <Label>Loyer mensuel</Label>
                                            <NumberField ariaLabel="Loyer mensuel" value={settings.monthlyRent} onChange={v => onSettings({ monthlyRent: v })} suffix="€ / mois" step={10} />
                                        </label>
                                        <div className="space-y-2 sm:col-span-2">
                                            <Label help="tmi">Tranche marginale d'imposition</Label>
                                            <Segmented ariaLabel="TMI" value={String(settings.tmi)} onChange={v => onSettings({ tmi: Number(v) })}
                                                options={[0, 11, 30, 41, 45].map(t => ({ value: String(t), label: `${t} %` }))} />
                                        </div>
                                    </div>
                                )}

                                <div className="border-t border-line pt-5">
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => setShowAdvanced(s => !s)} aria-expanded={showAdvanced} className="flex items-center gap-2 text-sm text-ink-soft hover:text-ink">
                                            <ChevronDown size={16} className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                                            Contraintes du chantier (facultatif)
                                        </button>
                                        <Help topic="siteConstraints" />
                                    </div>
                                    {showAdvanced && (
                                        <div className="mt-5 grid gap-5 sm:grid-cols-2">
                                            <label className="space-y-2 block">
                                                <Label>Étage du logement</Label>
                                                <NumberField ariaLabel="Étage" value={settings.nbEtages} onChange={v => onSettings({ nbEtages: v === '' ? '' : Math.round(v) })} suffix="0 = rez-de-chaussée" />
                                            </label>
                                            <div className="space-y-2">
                                                <Label>Ascenseur</Label>
                                                <div className="flex items-center gap-3 h-11">
                                                    <Switch checked={settings.hasAscenseur} onChange={v => onSettings({ hasAscenseur: v })} label="Ascenseur" />
                                                    <span className="text-sm text-muted">{settings.hasAscenseur ? 'Oui' : 'Non'}</span>
                                                </div>
                                            </div>
                                            <div className="space-y-2">
                                                <Label>Centre-ville dense</Label>
                                                <div className="flex items-center gap-3 h-11">
                                                    <Switch checked={settings.isUrbanDense} onChange={v => onSettings({ isUrbanDense: v })} label="Centre-ville dense" />
                                                    <span className="text-sm text-muted">{settings.isUrbanDense ? 'Oui (+10 %, stationnement)' : 'Non'}</span>
                                                </div>
                                            </div>
                                            {settings.isUrbanDense && (
                                                <label className="space-y-2 block">
                                                    <Label>Stationnement des artisans</Label>
                                                    <NumberField ariaLabel="Coût du stationnement" value={settings.parkingCost} onChange={v => onSettings({ parkingCost: v })} suffix="€ / jour" />
                                                </label>
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </Step>

                        {/* 4. Financing */}
                        <Step n={4} title="Votre plan de financement" subtitle="Du coût des travaux à ce qu'il vous reste à payer.">
                            {!sim || sim.cost === 0 ? (
                                <p className="text-sm text-muted">Sélectionnez des travaux à l'étape 2 pour afficher le plan de financement.</p>
                            ) : (
                                <div className="space-y-8">
                                    <div className="grid gap-8 md:grid-cols-2">
                                        <div>
                                            <p className="text-ink font-medium mb-2 flex items-center gap-1.5">Travaux <Help topic="cost" /></p>
                                            <div className="divide-y divide-line/70">
                                                {sim.detailedCosts.map(c => <Row key={c.id} label={c.name} value={eurRange(c.cost_low, c.cost_high)} />)}
                                                <Row label="Total TTC" value={eurRange(sim.costLow, sim.costHigh)} strong />
                                            </div>
                                        </div>
                                        <div>
                                            <p className="text-ink font-medium mb-2">Aides</p>
                                            <div className="divide-y divide-line/70">
                                                <Row
                                                    label={sim.aidPathway === 'accompagne' ? "MaPrimeRénov' rénovation d'ampleur" : "MaPrimeRénov' par geste"}
                                                    help={sim.aidPathway === 'accompagne' ? 'pathway' : 'mpr'}
                                                    value={`− ${eur(sim.sub)}`} tone={sim.sub > 0 ? 'positive' : 'muted'}
                                                />
                                                <Row label="Primes CEE (estimation)" help="cee" value={`− ${eur(sim.ceeEst)}`} tone={sim.ceeEst > 0 ? 'positive' : 'muted'} />
                                                <Row label="Reste à charge" help="rest" value={eurRange(sim.restLow, sim.restHigh)} strong />
                                                {sim.ecoPTZAmount > 0 && <Row label="Dont finançable par Éco-PTZ" help="ecoPtz" value={eur(sim.ecoPTZAmount)} tone="muted" />}
                                            </div>
                                            {sim.aidBlockers.length > 0 && ['E', 'F', 'G'].includes(sim.currentLabel) && (
                                                <div className="mt-3 text-sm text-ink-soft">
                                                    <p className="text-brass-light">Pourquoi pas la rénovation d'ampleur ?</p>
                                                    <ul className="mt-1 list-disc pl-5 space-y-1">{sim.aidBlockers.map(b => <li key={b}>{b}</li>)}</ul>
                                                </div>
                                            )}
                                            {sim.aidNotes.map(n => (
                                                <p key={n} className="mt-3 text-sm text-brass-light flex gap-2"><Info size={16} className="shrink-0 mt-0.5" />{n}</p>
                                            ))}
                                            <p className="mt-3 text-xs text-faint">Catégorie de revenus retenue : {sim.incomeProfile}.</p>
                                        </div>
                                    </div>

                                    {settings.isInvestor && (
                                        <div>
                                            <p className="text-ink font-medium mb-3">Rentabilité locative</p>
                                            <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
                                                {[
                                                    { label: 'Rendement brut', help: 'yield' as const, value: `${sim.yieldBrut.toFixed(1).replace('.', ',')} %` },
                                                    { label: 'Trésorerie mensuelle', help: 'cashflow' as const, value: eur(sim.cashflow) },
                                                    { label: "Économie d'impôt", help: 'taxBenefit' as const, value: eur(sim.taxBenefit) },
                                                    { label: 'Coût net après impôt', help: 'taxBenefit' as const, value: eur(sim.netInvestorCost) },
                                                ].map(k => (
                                                    <div key={k.label} className="rounded-xl bg-raised p-4">
                                                        <p className="text-xs text-muted flex items-center gap-1.5">{k.label} <Help topic={k.help} /></p>
                                                        <p className="mt-1 text-lg text-ink tabular-nums">{k.value}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <div className="border-t border-line pt-6 space-y-2">
                                        <p className="text-ink font-medium mb-1">Comprendre les aides</p>
                                        {[
                                            { title: "MaPrimeRénov'", text: "Demandée sur maprimerenov.gouv.fr avant le début des travaux. Les travaux doivent être réalisés par des artisans RGE. En rénovation d'ampleur, un Accompagnateur Rénov' (dont le coût est en partie pris en charge) vous suit pendant tout le projet." },
                                            { title: 'Primes CEE', text: "Proposées par les fournisseurs d'énergie et leurs partenaires. Comparez les offres et acceptez-les avant de signer le devis : une prime demandée après la signature est refusée." },
                                            { title: 'Éco-prêt à taux zéro', text: "Demandé auprès d'une banque partenaire avec les devis RGE. Il finance le reste à charge sans intérêts et se cumule avec MaPrimeRénov'." },
                                        ].map(item => (
                                            <details key={item.title} className="group rounded-xl border border-line px-4 py-3">
                                                <summary className="cursor-pointer list-none flex items-center justify-between text-sm text-ink-soft group-open:text-ink">
                                                    {item.title}
                                                    <ChevronDown size={16} className="transition-transform group-open:rotate-180" />
                                                </summary>
                                                <p className="mt-2 text-sm text-muted leading-relaxed">{item.text}</p>
                                            </details>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </Step>

                        <RgeCompanies property={property} actions={actions} />

                        <p className="text-xs text-faint leading-relaxed px-1">
                            Simulation indicative fondée sur les données publiques de l'ADEME et des coûts moyens de marché. Elle ne constitue ni un DPE, ni un audit énergétique réglementaire, ni un devis.
                            Les montants d'aides ({sims[scenario]?.aidRules || "barème MaPrimeRénov' en vigueur"}) doivent être confirmés par France Rénov' ou un Accompagnateur Rénov' avant tout engagement.
                        </p>
                    </div>
                </div>
            </main>

            <SiteFooter className="mt-10" />
        </div>
    );
}
