import { useEffect, useRef, useState } from 'react';
import { Check, Loader2 } from 'lucide-react';

export interface LoadingStep {
    label: string;
    detail: string; // technical line shown under the running step
}

// Steps of the dwelling analysis (simulator) and of the prospection map
export const SIMULATION_STEPS: LoadingStep[] = [
    { label: 'Interrogation de la base nationale des DPE', detail: 'ADEME · observatoire DPE-Audit · requête géolocalisée' },
    { label: 'Extraction des données thermiques du logement', detail: 'Parois, menuiseries, générateurs, consommations par usage' },
    { label: "Modélisation de l'enveloppe et des déperditions", detail: 'Surfaces déperditives · coefficients U · ponts thermiques' },
    { label: 'Calcul des scénarios de travaux', detail: 'Gains par poste · nouvelle consommation · étiquette cible' },
    { label: "Application des barèmes d'aides 2026", detail: "MaPrimeRénov' · primes CEE · éco-PTZ · plafonds de ressources" },
    { label: 'Estimation de la valeur verte', detail: 'Ventes DVF comparables · décote par classe énergétique' },
];

export const PROSPECTION_STEPS: LoadingStep[] = [
    { label: "Connexion aux données DPE de l'ADEME", detail: 'Diagnostics récents · filtrage par classe et par date' },
    { label: 'Géocodage des adresses', detail: "Base Adresse Nationale · rattachement à l'emprise de la carte" },
    { label: 'Regroupement des logements par adresse', detail: 'Immeubles, lots, dédoublonnage des diagnostics' },
    { label: 'Calcul des priorités de prospection', detail: 'Ancienneté du DPE · classe énergétique · interdictions de louer' },
    { label: 'Préparation de la carte', detail: 'Rendu des marqueurs et des fiches adresse' },
];

export const BUILDING_STEPS: LoadingStep[] = [
    { label: 'Interrogation de la base nationale des bâtiments', detail: 'BDNB · immeubles de 3 logements ou plus' },
    { label: 'Identification des propriétaires personnes morales', detail: 'Fichiers fonciers · SCI et sociétés privées, hors copropriétés' },
    { label: 'Croisement avec les DPE', detail: "ADEME · étiquette du bâtiment et des logements" },
    { label: 'Recherche des signaux de vente', detail: 'BODACC · dissolutions, liquidations, changements de dirigeant' },
    { label: 'Préparation de la carte', detail: 'Rendu des immeubles et des fiches société' },
];

export const INVEST_STEPS: LoadingStep[] = [
    { label: 'Collecte des DPE récents du secteur', detail: 'ADEME · logements classés E, F ou G' },
    { label: 'Programme de travaux de chaque logement', detail: 'Moteur SPREA · coûts, aides, classe atteinte' },
    { label: 'Valeur avant et après travaux', detail: 'Ventes DVF comparables · écarts de prix par classe DPE' },
    { label: 'Loyers de marché de la commune', detail: 'Carte des loyers ANIL' },
    { label: 'Classement des biens', detail: 'Potentiel de revalorisation · fraîcheur du DPE · valeur' },
];

const STEP_MS = 750;      // pace of one step
const MIN_MS = 3800;      // the sequence always runs at least this long
const MAX_MS = 25000;     // never blocks longer than this
const HOLD = 0.08;        // the last bar waits at 92 % until the data is there

interface Props {
    steps: LoadingStep[];
    title: string;
    subtitle?: string;
    done: boolean;             // data ready
    onFinished: () => void;    // called once the bars are full
    variant?: 'screen' | 'panel'; // full screen, or over its positioned parent
    sources: string;
}

export default function LoadingSequence({ steps, title, subtitle, done, onFinished, variant = 'screen', sources }: Props) {
    const n = steps.length;
    const [progress, setProgress] = useState(0); // 0 → n, one unit per step
    const doneRef = useRef(done);
    doneRef.current = done;
    const finishedRef = useRef(onFinished);
    finishedRef.current = onFinished;

    useEffect(() => {
        const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        const start = performance.now();
        let last = start;
        let p = 0;
        let frame = 0;
        let endTimer: ReturnType<typeof setTimeout> | undefined;
        const tick = (now: number) => {
            const dt = now - last;
            last = now;
            const elapsed = now - start;
            const finishing = (doneRef.current && elapsed >= MIN_MS) || elapsed >= MAX_MS;
            if (finishing) {
                p = Math.min(n, p + (dt / STEP_MS) * 5);
            } else if (p < n - 1) {
                p += dt / STEP_MS;
            } else {
                // Last step: slows down as it nears its hold point
                const cap = n - HOLD;
                p += Math.max(0, cap - p) * Math.min(1, dt / 900);
            }
            setProgress(p);
            if (p >= n) {
                endTimer = setTimeout(() => finishedRef.current(), reduced ? 0 : 350);
                return;
            }
            frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
        return () => { cancelAnimationFrame(frame); clearTimeout(endTimer); };
    }, [n]);

    const total = Math.round((progress / n) * 100);
    const current = Math.min(n - 1, Math.floor(progress));
    const position = variant === 'screen' ? 'fixed z-[2000]' : 'absolute z-[1100]';

    return (
        <div className={`${position} inset-0 flex overflow-y-auto bg-canvas/90 backdrop-blur-md px-4 py-4`}
            role="status" aria-live="polite" aria-label={`${title} : ${total} %`}>
            <div className="m-auto w-full max-w-lg rounded-2xl border border-line bg-panel/95 shadow-2xl shadow-black/50 p-6 sm:p-7">
                <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-brass">SPREA · moteur d'analyse</p>
                        <h2 className="mt-1.5 text-xl sm:text-2xl text-ink leading-tight">{title}</h2>
                        {subtitle && <p className="mt-1 text-sm text-muted truncate">{subtitle}</p>}
                    </div>
                    <span className="font-serif text-3xl sm:text-4xl text-brass-light tabular-nums shrink-0">{total}<span className="text-lg text-muted"> %</span></span>
                </div>

                <div className="mt-5 h-1 rounded-full bg-raised overflow-hidden">
                    <div className="h-full rounded-full bg-gradient-to-r from-brass-dark via-brass to-brass-light" style={{ width: `${total}%` }} />
                </div>

                <ol className="mt-6 space-y-3.5">
                    {steps.map((step, i) => {
                        const fill = Math.max(0, Math.min(1, progress - i));
                        const state = fill >= 1 ? 'done' : i === current ? 'running' : 'waiting';
                        return (
                            <li key={step.label} className={state === 'waiting' ? 'opacity-40' : ''}>
                                <div className="flex items-center gap-3">
                                    <span className={`h-5 w-5 shrink-0 rounded-full flex items-center justify-center ${state === 'done' ? 'bg-sage/15 text-sage' : state === 'running' ? 'text-brass' : 'border border-line'}`}>
                                        {state === 'done' ? <Check size={13} strokeWidth={3} /> : state === 'running' ? <Loader2 size={14} className="motion-safe:animate-spin" /> : null}
                                    </span>
                                    <span className={`flex-1 min-w-0 text-sm ${state === 'running' ? 'text-ink' : 'text-ink-soft'}`}>{step.label}</span>
                                    <span className="text-xs text-faint tabular-nums w-11 shrink-0 whitespace-nowrap text-right">{Math.round(fill * 100)} %</span>
                                </div>
                                <div className="mt-1.5 ml-8 h-1.5 rounded-full bg-raised overflow-hidden">
                                    <div className={`relative h-full rounded-full overflow-hidden ${state === 'done' ? 'bg-sage/80' : 'bg-brass'}`} style={{ width: `${fill * 100}%` }}>
                                        {state === 'running' && <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent motion-safe:animate-shimmer" />}
                                    </div>
                                </div>
                                {state === 'running' && (
                                    <p className="mt-1.5 ml-8 font-mono text-[11px] text-faint truncate">
                                        [{String(i + 1).padStart(2, '0')}/{String(n).padStart(2, '0')}] {step.detail}
                                    </p>
                                )}
                            </li>
                        );
                    })}
                </ol>

                <p className="mt-6 pt-4 border-t border-line text-[11px] text-faint">
                    Sources officielles : {sources}.
                </p>
            </div>
        </div>
    );
}
