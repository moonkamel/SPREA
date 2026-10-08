import { LEGAL } from '../legal';
import { LegalPage, LegalSection } from './site';

// Last update of this policy: change it whenever the data processing changes
const UPDATED = '8 octobre 2026';

const th = 'text-left font-semibold text-ink p-3 align-top';
const td = 'p-3 align-top border-t border-line text-ink-soft';

export default function ConfidentialitePage() {
    return (
        <LegalPage title="Politique de confidentialité" updated={`Mise à jour le ${UPDATED}`}>
            <LegalSection title="Responsable du traitement">
                <p>{LEGAL.companyName}, {LEGAL.address}, est responsable des traitements de données personnelles réalisés sur {LEGAL.brand}. Contact pour toute question ou demande : {LEGAL.email}.</p>
            </LegalSection>

            <LegalSection title="Données traitées, finalités et bases légales">
                <div className="overflow-x-auto -mx-2">
                    <table className="w-full text-sm min-w-[560px] border border-line rounded-xl overflow-hidden">
                        <thead className="bg-raised">
                            <tr><th className={th}>Situation</th><th className={th}>Données</th><th className={th}>Finalité</th><th className={th}>Base légale</th></tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td className={td}>Simulation, sans compte</td>
                                <td className={td}>Adresse ou numéro de DPE recherché, paramètres saisis (revenus du foyer par tranche, étages, loyer, prix d'achat…)</td>
                                <td className={td}>Calculer la simulation. Ces données ne sont pas enregistrées par le site.</td>
                                <td className={td}>Intérêt légitime (fournir le service demandé)</td>
                            </tr>
                            <tr>
                                <td className={td}>Demande de rappel sur une page d'agence (lien ou QR code reçu par courrier)</td>
                                <td className={td}>Nom, téléphone et/ou email, message, date et texte du consentement</td>
                                <td className={td}>Transmettre la demande à l'agence qui a envoyé le courrier, seule destinataire. L'agence est responsable de ce traitement ; SPREA l'héberge pour son compte (sous-traitant). Le site compte aussi les visites de la page, sans donnée personnelle.</td>
                                <td className={td}>Consentement de la personne, recueilli par l'agence</td>
                            </tr>
                            <tr>
                                <td className={td}>Compte</td>
                                <td className={td}>Adresse email, identifiant de compte, dates de connexion</td>
                                <td className={td}>Créer le compte et permettre la connexion par lien email</td>
                                <td className={td}>Exécution du contrat</td>
                            </tr>
                            <tr>
                                <td className={td}>Rapports</td>
                                <td className={td}>Adresse et caractéristiques du logement, paramètres de la simulation (dont tranche de revenus, données d'investissement le cas échéant), texte d'analyse généré</td>
                                <td className={td}>Produire le rapport et permettre de le retélécharger</td>
                                <td className={td}>Exécution du contrat</td>
                            </tr>
                            <tr>
                                <td className={td}>Achats et abonnement</td>
                                <td className={td}>Identifiant client Stripe, statut de l'abonnement, montants, date et version des CGV acceptées (y compris les conditions d'utilisation de la carte de prospection). Les données de carte bancaire sont saisies chez Stripe et ne sont jamais transmises au site.</td>
                                <td className={td}>Encaisser, facturer, gérer l'abonnement, prouver l'acceptation des CGV</td>
                                <td className={td}>Exécution du contrat, obligations légales (comptabilité)</td>
                            </tr>
                            <tr>
                                <td className={td}>Analyse d'un PDF de DPE (compte requis)</td>
                                <td className={td}>Contenu du document envoyé</td>
                                <td className={td}>Extraire les informations du DPE. Le document n'est pas conservé.</td>
                                <td className={td}>Exécution du contrat</td>
                            </tr>
                            <tr>
                                <td className={td}>Toute visite</td>
                                <td className={td}>Adresse IP, journaux techniques</td>
                                <td className={td}>Sécurité, limitation des abus, diagnostic des erreurs</td>
                                <td className={td}>Intérêt légitime</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <p>Le site ne fait pas de publicité ciblée, ne vend pas de données et ne prend aucune décision automatisée produisant des effets juridiques à votre égard.</p>
            </LegalSection>

            <LegalSection title="Destinataires et sous-traitants">
                <p>Les données sont accessibles uniquement à l'éditeur et aux prestataires nécessaires au service, qui agissent sur ses instructions :</p>
                <ul className="list-disc pl-5 space-y-1">
                    <li><b>Vercel</b> (États-Unis) : hébergement du site et de l'API.</li>
                    <li><b>Supabase</b> (région {LEGAL.databaseRegion}) : comptes, authentification, base de données, envoi des liens de connexion.</li>
                    <li><b>Stripe</b> (Irlande, États-Unis) : paiement, factures, gestion de l'abonnement.</li>
                    <li><b>Anthropic</b> (États-Unis) : rédaction de l'analyse du rapport par le modèle Claude, à partir des caractéristiques et chiffres du logement et de sa commune, sans votre email ni le numéro et la rue du bien. Ces données ne servent pas à entraîner ses modèles.</li>
                    <li><b>OpenAI</b> : extraction des informations d'un PDF de DPE, uniquement si vous utilisez cette fonction.</li>
                    <li><b>Services publics</b> : l'adresse recherchée est transmise à la Base Adresse Nationale (adresse.data.gouv.fr) pour la localiser, et à l'ADEME pour retrouver le DPE.</li>
                </ul>
                <p>Certains prestataires sont situés hors de l'Union européenne. Ces transferts sont encadrés par le cadre de protection des données UE–États-Unis (Data Privacy Framework) pour les entreprises certifiées, ou par les clauses contractuelles types de la Commission européenne.</p>
            </LegalSection>

            <LegalSection title="Durées de conservation">
                <ul className="list-disc pl-5 space-y-1">
                    <li>Compte et rapports : jusqu'à la suppression du compte, effacés immédiatement à ce moment.</li>
                    <li>Demandes de rappel laissées sur une page d'agence : jusqu'à leur suppression par l'agence, à la suppression de son compte ou au plus tard 3 ans après leur envoi. Pour exercer vos droits, adressez-vous à l'agence indiquée sur la page, ou à nous : nous transmettrons.</li>
                    <li>Factures et pièces comptables : 10 ans (Code de commerce, art. L123-22).</li>
                    <li>Après suppression du compte, trace minimale des achats et des acceptations (date, montant, références de paiement, version des CGV ou des conditions de la carte de prospection acceptée), sans email, adresse ni simulation : 5 ans (prescription), comme preuve en cas de litige.</li>
                    <li>Journaux techniques : quelques jours, selon la politique de l'hébergeur.</li>
                    <li>Données de simulation sans compte : non conservées.</li>
                </ul>
            </LegalSection>

            <LegalSection title="Cookies et stockage local">
                <p>Le site n'utilise ni cookie publicitaire, ni outil de mesure d'audience. Il enregistre dans votre navigateur uniquement des éléments strictement nécessaires, exemptés de consentement :</p>
                <ul className="list-disc pl-5 space-y-1">
                    <li>votre session de connexion (Supabase), tant que vous êtes connecté ;</li>
                    <li>la simulation en attente lorsque vous vous connectez pour obtenir un rapport, effacée une fois le rapport demandé.</li>
                </ul>
                <p>La page de paiement est hébergée par Stripe, qui y dépose ses propres cookies nécessaires à la sécurité des paiements et à la lutte contre la fraude.</p>
            </LegalSection>

            <LegalSection title="Vos droits">
                <p>Vous disposez d'un droit d'accès, de rectification, d'effacement, de limitation, d'opposition et de portabilité de vos données, ainsi que du droit de définir des directives sur leur sort après votre décès. Vous pouvez supprimer votre compte à tout moment depuis « Mon compte », rubrique « Supprimer mon compte ». Pour exercer vos autres droits, écrivez à {LEGAL.email} depuis l'adresse email de votre compte. Une réponse vous est apportée dans un délai d'un mois.</p>
                <p>Vous pouvez introduire une réclamation auprès de la CNIL (www.cnil.fr).</p>
            </LegalSection>

            <LegalSection title="Sécurité">
                <p>Les échanges sont chiffrés (HTTPS). L'accès aux comptes se fait par lien de connexion à usage unique, sans mot de passe stocké. La base de données n'est accessible qu'au serveur du site ; chaque rapport n'est visible que par son propriétaire.</p>
            </LegalSection>
        </LegalPage>
    );
}
