import { ArrowLeft, ChevronRight } from 'lucide-react';
import { DpeBadge, Help } from '../ui';
import { SiteFooter, SiteHeader } from '../pages/site';
import { capitalize, formatDate, type PropertyData } from '../model';

interface Props {
    results: PropertyData[];
    onSelect: (p: PropertyData) => void;
    onBack: () => void;
}

export default function Results({ results, onSelect, onBack }: Props) {
    return (
        <div className="min-h-screen flex flex-col">
            <SiteHeader onHome={onBack} />
            <main className="flex-1 max-w-3xl w-full mx-auto px-4 sm:px-6 py-10">
                <button onClick={onBack} className="flex items-center gap-2 text-sm text-muted hover:text-ink mb-8">
                    <ArrowLeft size={16} /> Nouvelle recherche
                </button>
                <h1 className="text-3xl text-ink">
                    {results.length > 1 ? `${results.length} diagnostics trouvés` : 'Diagnostic trouvé'}
                </h1>
                <p className="mt-2 text-muted flex items-center gap-2">
                    {results.length > 1 ? 'Sélectionnez celui de votre logement.' : 'Vérifiez qu\'il correspond à votre logement.'}
                    {results.length > 1 && <Help topic="multipleDpe" />}
                </p>

                <ul className="mt-8 space-y-3">
                    {results.map(r => (
                        <li key={`${r.ademe_dpe_number}-${r.address}`}>
                            <button onClick={() => onSelect(r)}
                                className="w-full text-left rounded-2xl border border-line bg-panel hover:border-brass/60 hover:bg-raised transition-colors p-5 flex items-center gap-5 group">
                                <DpeBadge label={r.label} size="lg" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-ink font-medium truncate">{r.address}{r.city && !r.address.includes(r.postcode || '#') ? `, ${[r.postcode, r.city].filter(Boolean).join(' ')}` : ''}</p>
                                    <p className="text-sm text-muted mt-1">
                                        {[capitalize(r.buildingType), r.surface ? `${r.surface} m²` : null, r.constructionPeriod || r.year].filter(Boolean).join(' · ')}
                                    </p>
                                    <p className="text-xs text-faint mt-1">
                                        {r.dpeDate ? `DPE du ${formatDate(r.dpeDate)}` : 'DPE'}{r.ademe_dpe_number ? ` · n° ${r.ademe_dpe_number}` : ''}
                                    </p>
                                </div>
                                <ChevronRight className="text-faint group-hover:text-brass shrink-0" />
                            </button>
                        </li>
                    ))}
                </ul>
            </main>
            <SiteFooter />
        </div>
    );
}
