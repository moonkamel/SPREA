import { useState } from 'react';
import { Loader2, Users } from 'lucide-react';
import { Button, Card } from '../ui';
import { saveJoinToken, useAccount } from '../account';
import { Link } from '../router';
import { PageShell } from './site';
import { useSeo } from '../seo';

// Invitation link: /rejoindre?token=...
// The join itself is done by the account (joinTeam), once per token.
export default function JoinPage() {
    useSeo({ title: 'Équipe · SPREA', noindex: true });
    const { session, openLogin, joinTeam } = useAccount();
    const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '');
    const [accepted, setAccepted] = useState(false);
    const [joining, setJoining] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const join = async () => {
        if (!accepted || joining) return;
        setJoining(true);
        setError(null);
        const err = await joinTeam(token);
        // On success, joinTeam navigates to the simulator
        if (err) { setError(err); setJoining(false); }
    };

    return (
        <PageShell>
            <Card className="max-w-lg mx-auto p-8 text-center">
                <Users className="mx-auto text-brass" />
                <h1 className="mt-4 text-2xl text-ink">Rejoindre votre agence sur SPREA</h1>
                {!token ? (
                    <p className="mt-3 text-muted">Ce lien d'invitation est incomplet : ouvrez le lien reçu par email.</p>
                ) : (
                    <>
                        <p className="mt-3 text-muted">
                            {session
                                ? 'Acceptez les conditions générales de vente pour activer votre accès.'
                                : "Connectez-vous avec l'adresse email à laquelle l'invitation a été envoyée : votre accès sera activé aussitôt."}
                        </p>
                        <label className="mt-6 flex items-start gap-3 text-left text-sm text-ink-soft">
                            <input type="checkbox" required checked={accepted} onChange={e => setAccepted(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brass shrink-0" />
                            <span>J'accepte les <Link to="/cgv" className="text-brass underline">conditions générales de vente (CGV)</Link>.</span>
                        </label>
                        {error && <p role="alert" className="mt-4 text-sm text-coral">{error}</p>}
                        {session ? (
                            <Button className="mt-6" disabled={!accepted || joining} onClick={join}>
                                {joining && <Loader2 className="animate-spin" size={16} />} Rejoindre l'agence
                            </Button>
                        ) : (
                            <Button className="mt-6" disabled={!accepted} onClick={() => { saveJoinToken(token); openLogin('Connectez-vous avec l’adresse email invitée.'); }}>
                                Se connecter
                            </Button>
                        )}
                    </>
                )}
            </Card>
        </PageShell>
    );
}
