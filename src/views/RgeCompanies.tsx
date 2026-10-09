import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, Loader2, Phone } from 'lucide-react';
import { Step } from '../ui';
import { useAccount } from '../account';
import type { PropertyData, RetrofitAction } from '../model';

interface Company { siret: string | null; name: string; city: string; phone: string | null; website: string | null; distance_km: number }
interface Result { works: Record<string, Company[]>; global: Company[]; audit: Company[] }

const km = (d: number) => `${d.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} km`;
const site = (url: string) => (/^https?:\/\//.test(url) ? url : `https://${url}`);

function CompanyLine({ c }: { c: Company }) {
    return (
        <li className="py-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
            <span className="text-ink">{c.name} <span className="text-faint">· {c.city} · {km(c.distance_km)}</span></span>
            <span className="flex items-center gap-3 text-xs">
                {c.phone && <a href={`tel:${c.phone.replace(/[^0-9+]/g, '')}`} className="flex items-center gap-1 text-brass-light hover:underline"><Phone size={12} />{c.phone}</a>}
                {c.website && <a href={site(c.website)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-muted hover:text-ink"><ExternalLink size={12} />Site</a>}
            </span>
        </li>
    );
}

// Qualified companies near the dwelling for each selected work (ADEME RGE directory)
export default function RgeCompanies({ property, actions }: { property: PropertyData; actions: RetrofitAction[] }) {
    const { authedFetch } = useAccount();
    const works = useMemo(() => actions.filter(a => a.active).map(a => a.id).sort().join(','), [actions]);
    const [data, setData] = useState<Result | null>(null);
    const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');

    useEffect(() => {
        if (property.latitude == null || property.longitude == null || !works) { setData(null); return; }
        const controller = new AbortController();
        setState('loading');
        const timer = setTimeout(async () => {
            try {
                const params = new URLSearchParams({ lat: String(property.latitude), lon: String(property.longitude), works, kind: property.buildingType || '' });
                const res = await authedFetch(`/api/rge?${params}`, { signal: controller.signal });
                if (!res.ok) throw new Error();
                setData(await res.json());
                setState('idle');
            } catch (e) {
                if ((e as Error).name !== 'AbortError') setState('error');
            }
        }, 400);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [property.latitude, property.longitude, property.buildingType, works, authedFetch]);

    if (property.latitude == null || !works) return null;
    const names = Object.fromEntries(actions.map(a => [a.id, a.name]));
    const groups: [string, Company[]][] = data ? [
        ...Object.entries(data.works).filter(([, list]) => list.length).map(([id, list]) => [names[id] || id, list] as [string, Company[]]),
        ...(data.global.length ? [['Rénovation globale (un seul interlocuteur)', data.global] as [string, Company[]]] : []),
        ...(data.audit.length ? [['Audit énergétique', data.audit] as [string, Company[]]] : []),
    ] : [];

    return (
        <Step n={5} title="Des artisans RGE près du logement" subtitle="Les aides ne sont versées que pour des travaux réalisés par une entreprise RGE.">
            {state === 'loading' && !data && <Loader2 className="animate-spin text-faint" />}
            {state === 'error' && <p className="text-sm text-muted">L'annuaire RGE de l'ADEME ne répond pas pour le moment.</p>}
            {data && groups.length === 0 && <p className="text-sm text-muted">Aucune entreprise RGE trouvée à moins de 50 km pour ces travaux.</p>}
            <div className="space-y-5">
                {groups.map(([title, list]) => (
                    <div key={title}>
                        <p className="text-sm font-medium text-ink-soft">{title}</p>
                        <ul className="mt-1 divide-y divide-line/60">{list.map(c => <CompanyLine key={`${title}-${c.siret || c.name}`} c={c} />)}</ul>
                    </div>
                ))}
            </div>
            {groups.length > 0 && (
                <p className="mt-4 text-xs text-faint">
                    Entreprises qualifiées les plus proches d'après l'annuaire public de l'ADEME, sans classement ni recommandation. Elles figurent aussi dans le rapport PDF.
                </p>
            )}
        </Step>
    );
}
