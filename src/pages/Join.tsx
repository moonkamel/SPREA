import { useEffect, useState } from 'react';
import { Loader2, Users } from 'lucide-react';
import { Button, Card } from '../ui';
import { saveJoinToken, useAccount } from '../account';
import { navigate } from '../router';
import { PageShell } from './site';
import { useSeo } from '../seo';

// Invitation link: /rejoindre?token=...
export default function JoinPage() {
    useSeo({ title: 'Équipe · SPREA', noindex: true });
    const { session, openLogin, authedFetch, refreshMe } = useAccount();
    const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '');
    const [status, setStatus] = useState<'idle' | 'joining' | 'error'>('idle');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!token || !session || status !== 'idle') return;
        setStatus('joining');
        (async () => {
            const res = await authedFetch('/api/team/join', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }),
            });
            if (!res.ok) {
                try { setError((await res.json()).detail); } catch { setError("L'invitation n'a pas pu être acceptée."); }
                setStatus('error');
                return;
            }
            await refreshMe();
            navigate('/');
        })();
    }, [token, session, status, authedFetch, refreshMe]);

    return (
        <PageShell>
            <Card className="max-w-lg mx-auto p-8 text-center">
                <Users className="mx-auto text-brass" />
                <h1 className="mt-4 text-2xl text-ink">Rejoindre votre agence sur SPREA</h1>
                {!token ? (
                    <p className="mt-3 text-muted">Ce lien d'invitation est incomplet : ouvrez le lien reçu par email.</p>
                ) : status === 'error' ? (
                    <p role="alert" className="mt-3 text-coral">{error}</p>
                ) : session ? (
                    <Loader2 className="mt-6 mx-auto animate-spin text-faint" />
                ) : (
                    <>
                        <p className="mt-3 text-muted">Connectez-vous avec l'adresse email à laquelle l'invitation a été envoyée : votre accès sera activé aussitôt.</p>
                        <Button className="mt-6" onClick={() => { saveJoinToken(token); openLogin('Connectez-vous avec l’adresse email invitée.'); }}>
                            Se connecter
                        </Button>
                    </>
                )}
            </Card>
        </PageShell>
    );
}
