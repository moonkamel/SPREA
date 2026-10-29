import { useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { navigate } from './router';

// In-app guided tour: bubbles anchored on the real elements of the screen,
// one sentence per step, "Passer" at every step, started once on its own and
// again from the header. Two journeys:
// - "command": the welcome, then Prospection, the agent's one prospecting
//   dashboard (the id stays "command" so the agents who saw it are not shown it again);
// - "vendre": sell a poorly rated dwelling under mandate with the buyer's file.
// A journey may span two screens (the simulator's search, then its results):
// each screen hosts the steps it can show.

export type TourId = 'command' | 'vendre';
export type TourScreen = 'simulateur' | 'logement' | 'prospection';

interface TourStep {
    screen: TourScreen;
    // data-tour attribute of the element the bubble points to
    target: string;
    title: string;
    text: string;
    note?: string;
    // Last step of a screen: where the button leads, and what the bubble says about it
    go?: string;
    then?: string;
}

export const TOURS: Record<TourId, { name: string; steps: TourStep[] }> = {
    command: {
        name: 'Bienvenue dans SPREA',
        steps: [
            { screen: 'simulateur', target: 'home-command', title: 'Prospection',
              text: 'Votre cockpit de prospection : les biens à fort potentiel de votre secteur, chiffrés et classés, et toutes les actions au même endroit.',
              go: '/prospection', then: 'La visite continue dans Prospection.' },
            { screen: 'prospection', target: 'cmd-kpis', title: 'Votre secteur ce matin',
              text: 'Nouveaux DPE, biens à fort potentiel, valeur à débloquer par la rénovation, signaux de vente des SCI, demandes de vendeurs.' },
            { screen: 'prospection', target: 'cmd-targets', title: 'Vos cibles',
              text: 'Classées par score : ce que la rénovation ajoute à la valeur, la fraîcheur du DPE, l\'urgence pour le propriétaire.',
              note: 'Au clavier : ↑ ↓ pour choisir, Entrée pour ouvrir.' },
            { screen: 'prospection', target: 'cmd-briefing', title: 'Par où commencer',
              text: 'Le briefing vous donne la priorité du jour. Une cible ouverte montre ses chiffres et toutes les actions : courrier, nom du propriétaire, dossiers.' },
            { screen: 'prospection', target: 'cmd-search', title: 'Votre zone',
              text: 'Tapez une commune ou une adresse pour scanner un autre secteur, ou une commande (⌘ K).' },
            { screen: 'prospection', target: 'cmd-layers', title: 'Toute la carte',
              text: 'Tous les DPE récents de la carte, les immeubles entiers détenus par une société, vos alertes du matin et la fiche DPE d\'un bien précis.' },
            { screen: 'prospection', target: 'cmd-suivi', title: 'Le suivi',
              text: 'De « à contacter » au mandat, avec chaque matin les relances dues et les vendeurs à rappeler.',
              note: 'Cette visite reste disponible dans le menu « ? » du site.' },
        ],
    },
    vendre: {
        name: 'Vendre une passoire',
        steps: [
            { screen: 'simulateur', target: 'sell-address', title: 'Votre bien',
              text: "Saisissez l'adresse du bien sous mandat, ou le numéro de son DPE." },
            { screen: 'logement', target: 'sell-summary', title: "L'analyse",
              text: 'Travaux, aides, nouvelle étiquette et valeur après rénovation sont chiffrés à partir de son DPE.' },
            { screen: 'logement', target: 'sell-works', title: 'Le projet',
              text: 'Cochez ou décochez des travaux : le dossier reprendra exactement ce programme.' },
            { screen: 'logement', target: 'sell-dossier', title: 'Le dossier acheteur',
              text: 'Partagez-le avec vos acquéreurs : ils ne voient plus une passoire, mais un projet chiffré.',
              note: 'Estimations indicatives, à confirmer par devis.' },
        ],
    },
};

const STATE_KEY = 'sprea-tour';
const SEEN_KEY = 'sprea-tour-seen-';
const EVENT = 'sprea:tour';

interface TourState { id: TourId; step: number }

function readState(): TourState | null {
    try {
        const s = JSON.parse(sessionStorage.getItem(STATE_KEY) || 'null');
        return s && TOURS[s.id as TourId] ? s : null;
    } catch {
        return null;
    }
}

function writeState(s: TourState | null) {
    try {
        if (s) sessionStorage.setItem(STATE_KEY, JSON.stringify(s));
        else sessionStorage.removeItem(STATE_KEY);
    } catch { /* storage blocked: the tour still runs on this screen */ }
    window.dispatchEvent(new Event(EVENT));
}

function markSeen(id: TourId) {
    try { localStorage.setItem(SEEN_KEY + id, '1'); } catch { /* ignore */ }
}

function seen(id: TourId): boolean {
    try { return localStorage.getItem(SEEN_KEY + id) === '1'; } catch { return true; }
}

// From the header menu: goes to the journey's first screen and starts it
export function startTour(id: TourId) {
    markSeen(id);
    writeState({ id, step: 0 });
    const first = TOURS[id].steps[0].screen;
    if (first === 'simulateur') navigate('/');
    else if (first === 'prospection') navigate('/prospection');
}

// Starts a journey the first time one of its screens is shown, at the
// first step of that screen
export function useAutoTour(id: TourId, enabled: boolean, step = 0) {
    useEffect(() => {
        if (!enabled || seen(id) || readState()) return;
        const timer = setTimeout(() => { markSeen(id); writeState({ id, step }); }, 900);
        return () => clearTimeout(timer);
    }, [id, enabled, step]);
}

function useTourState(): TourState | null {
    const [state, setState] = useState<TourState | null>(readState);
    useEffect(() => {
        const sync = () => setState(readState());
        window.addEventListener(EVENT, sync);
        return () => window.removeEventListener(EVENT, sync);
    }, []);
    return state;
}

// Where the target is on the screen, followed while the page scrolls or resizes
function useTargetRect(target: string | null): DOMRect | null {
    const [rect, setRect] = useState<DOMRect | null>(null);
    useLayoutEffect(() => {
        setRect(null);
        if (!target) return;
        let frame = 0;
        let tries = 0;
        const find = () => document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
        const measure = () => {
            const el = find();
            setRect(el && el.offsetParent !== null ? el.getBoundingClientRect() : null);
        };
        // The element may appear a moment later (results loading)
        const wait = () => {
            const el = find();
            if (el) {
                el.scrollIntoView({ block: 'center', behavior: 'smooth' });
                setTimeout(measure, 350);
            } else if (tries++ < 20) {
                frame = window.setTimeout(wait, 150);
            } else {
                setRect(null);
            }
        };
        wait();
        window.addEventListener('scroll', measure, true);
        window.addEventListener('resize', measure);
        return () => {
            clearTimeout(frame);
            window.removeEventListener('scroll', measure, true);
            window.removeEventListener('resize', measure);
        };
    }, [target]);
    return rect;
}

const BUBBLE_W = 320;
const GAP = 12;
const BUBBLE_H = 260;
// Sticky site header
const HEADER = 64;

export function TourHost({ screen }: { screen: TourScreen }) {
    const state = useTourState();
    const tour = state ? TOURS[state.id] : null;
    const step = tour && state ? tour.steps[state.step] : null;
    const here = !!step && step.screen === screen;
    const rect = useTargetRect(here ? step!.target : null);

    const close = useCallback(() => writeState(null), []);
    const next = useCallback(() => {
        if (!state || !tour) return;
        writeState(state.step + 1 < tour.steps.length ? { ...state, step: state.step + 1 } : null);
    }, [state, tour]);

    useEffect(() => {
        if (!here) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [here, close]);

    if (!here || !tour || !state || !step) return null;
    const last = state.step === tour.steps.length - 1;
    // The next step is on another screen: the agent gets there by using the tool
    const leaves = !last && tour.steps[state.step + 1].screen !== screen;

    // Bubble under the target, or above when there is no room; centred without target;
    // pinned to the bottom on a phone
    const phone = window.innerWidth < 640;
    let style: React.CSSProperties;
    if (phone || !rect) {
        style = phone ? { left: 16, right: 16, bottom: 16 } : { left: '50%', top: '40%', transform: 'translate(-50%, -50%)', width: BUBBLE_W };
    } else {
        const left = Math.min(Math.max(16, rect.left + rect.width / 2 - BUBBLE_W / 2), window.innerWidth - BUBBLE_W - 16);
        const tall = rect.height > window.innerHeight * 0.5;
        if (tall && rect.left > BUBBLE_W + 2 * GAP) style = { left: rect.left - BUBBLE_W - GAP, top: Math.max(HEADER + GAP, rect.top), width: BUBBLE_W };
        else if (tall && window.innerWidth - rect.right > BUBBLE_W + 2 * GAP) style = { left: rect.right + GAP, top: Math.max(HEADER + GAP, rect.top), width: BUBBLE_W };
        else if (rect.bottom + GAP + BUBBLE_H < window.innerHeight) style = { left, top: rect.bottom + GAP, width: BUBBLE_W };
        else if (rect.top - GAP - BUBBLE_H > HEADER) style = { left, bottom: Math.max(16, window.innerHeight - rect.top + GAP), width: BUBBLE_W };
        // A large target (the map): the bubble sits inside it, at its top
        else style = { left: Math.max(16, rect.left + 16), top: Math.max(HEADER + GAP, rect.top + 16), width: BUBBLE_W };
    }

    return (
        <>
            {rect && (
                <div aria-hidden className="fixed z-[1100] pointer-events-none rounded-xl ring-2 ring-brass-light transition-all duration-200"
                    style={{ left: rect.left - 4, top: rect.top - 4, width: rect.width + 8, height: rect.height + 8,
                             boxShadow: '0 0 0 9999px rgba(5, 8, 15, 0.55)' }} />
            )}
            <div role="dialog" aria-label={`Visite guidée : ${step.title}`}
                className="fixed z-[1101] rounded-2xl border border-brass/50 bg-panel p-4 shadow-2xl shadow-black/60" style={style}>
                <p className="text-[11px] text-brass tracking-wide">{tour.name} · {state.step + 1}/{tour.steps.length}</p>
                <p className="mt-1 text-ink font-medium">{step.title}</p>
                <p className="mt-1 text-sm text-ink-soft leading-relaxed">{step.text}</p>
                {step.note && <p className="mt-1.5 text-xs text-faint">{step.note}</p>}
                {leaves && <p className="mt-1.5 text-xs text-faint">{step.then || 'La visite reprend sur la fiche du logement.'}</p>}
                <div className="mt-3 flex items-center justify-between gap-3">
                    <button type="button" onClick={close} className="text-xs text-muted hover:text-ink">Passer</button>
                    <button type="button" onClick={leaves ? () => { writeState({ ...state, step: state.step + 1 }); if (step.go) navigate(step.go); } : next}
                        className="h-8 px-3 rounded-lg bg-brass text-canvas text-sm font-medium hover:bg-brass-light">
                        {last ? 'Terminer' : leaves ? (step.go ? 'Ouvrir' : 'Compris') : 'Suivant'}
                    </button>
                </div>
            </div>
        </>
    );
}
