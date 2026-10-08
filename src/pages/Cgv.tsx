import type { ReactNode } from 'react';
import { CGV_VERSION, LEGAL } from '../legal';
import { Link } from '../router';
import { LegalPage, LegalSection } from './site';

function Article({ n, title, children }: { n: number; title: string; children: ReactNode }) {
    return <LegalSection title={`Article ${n} – ${title}`}>{children}</LegalSection>;
}

export default function CgvPage() {
    const version = new Date(CGV_VERSION.slice(0, 10)).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    return (
        <LegalPage title="Conditions générales de vente"
            updated={`Version du ${version}${CGV_VERSION.length > 10 ? `, révision ${CGV_VERSION.slice(11)}` : ''}`}>

                <Article n={1} title="Objet et champ d'application">
                    <p>Les présentes conditions générales de vente (« CGV ») régissent les abonnements souscrits sur le site {LEGAL.brand} auprès de {LEGAL.companyName} (« le Vendeur ») par des professionnels, notamment de l'immobilier, agissant pour les besoins de leur activité professionnelle (« le Client »). Le site et ses services ne sont pas destinés aux consommateurs.</p>
                    <p>Le Client les accepte expressément avant la souscription en cochant la case prévue à cet effet. Les CGV applicables sont celles en vigueur à la date de la souscription ; les contrats Réseau peuvent comporter des conditions particulières, qui prévalent sur les CGV.</p>
                </Article>

                <Article n={2} title="Identification du Vendeur">
                    <p>
                        {LEGAL.companyName}, {LEGAL.legalForm}<br />
                        Siège social : {LEGAL.address}<br />
                        {LEGAL.registration}<br />
                        {LEGAL.vat}<br />
                        Contact : {LEGAL.email}
                    </p>
                </Article>

                <Article n={3} title="Services proposés">
                    <p>L'abonnement donne accès, pendant sa durée et sans limite d'usage raisonnable, aux services suivants : simulateur de rénovation à partir des données publiques du diagnostic de performance énergétique (DPE) publiées par l'ADEME (travaux, étiquette après travaux, aides, reste à charge, économies, valeur verte) ; rapports PDF ; avis de valeur avant et après travaux fondés sur les ventes publiées dans la base DVF ; carte de prospection et alertes sur les nouveaux DPE (article 14) ; courriers, pages de contact et suivi des demandes reçues.</p>
                    <p>Trois formules sont proposées : <b>Solo</b>, pour un utilisateur ; <b>Agence</b>, facturée par utilisateur, à partir de deux ; <b>Réseau</b>, pour plusieurs agences, sur devis et conditions particulières. Leurs caractéristiques et leurs prix sont présentés sur la page <Link to="/tarifs" className="underline text-brass hover:text-brass-light">Tarifs</Link> et rappelés avant le paiement.</p>
                </Article>

                <Article n={4} title="Nature des résultats">
                    <p>Les simulations et rapports sont des <b>estimations indicatives</b>, établies à partir des données publiques du DPE, de valeurs moyennes de construction et de coûts moyens de marché. Ils ne constituent ni un DPE, ni un audit énergétique réglementaire, ni un devis, ni une étude thermique, ni un conseil juridique, fiscal ou financier.</p>
                    <p>Les montants d'aides sont calculés selon les barèmes publics connus à la date de la simulation. Leur attribution dépend de conditions d'éligibilité vérifiées par les organismes compétents (Anah, fournisseurs d'énergie, banques) et doit être confirmée par France Rénov' ou un Accompagnateur Rénov' avant tout engagement. Les résultats dépendent de l'exactitude des données du DPE, dont le Vendeur n'est pas l'auteur.</p>
                </Article>

                <Article n={5} title="Compte et utilisateurs">
                    <p>L'accès aux services nécessite un compte, créé à partir d'une adresse email professionnelle ; la connexion s'effectue par un lien envoyé à cette adresse. Chaque compte est personnel et réservé à un seul utilisateur : le partage d'un accès entre plusieurs personnes est interdit, chaque utilisateur supplémentaire devant disposer de son propre abonnement ou d'une place dans une formule Agence ou Réseau.</p>
                    <p>Le Client est responsable de l'accès à sa messagerie et de l'usage fait de son compte. Il peut le supprimer à tout moment depuis l'espace « Mon compte » ; ses rapports et données ne sont alors plus accessibles.</p>
                </Article>

                <Article n={6} title="Prix">
                    <p>Les prix sont indiqués en euros hors taxes ; la TVA au taux en vigueur s'y ajoute et figure sur la facture. Le prix applicable est celui affiché au moment de la souscription.</p>
                    <p>Le Vendeur peut modifier ses prix. Le Client en est informé par email au moins 30 jours avant leur application ; le nouveau prix s'applique à la période suivante, et le Client peut résilier sans frais avant cette date.</p>
                </Article>

                <Article n={7} title="Souscription et paiement">
                    <p>La souscription est faite depuis le site : choix de la formule et de la périodicité (mensuelle ou annuelle), acceptation des CGV, puis paiement par carte bancaire sur la page sécurisée de notre prestataire Stripe, qui recueille la raison sociale, l'adresse et le numéro de TVA du Client. Le Vendeur n'a pas accès aux données de carte bancaire. Les formules Agence et Réseau peuvent aussi être souscrites sur devis.</p>
                    <p>L'abonnement est payable d'avance, au début de chaque période. Une facture est émise à chaque paiement et mise à disposition du Client dans « Mon compte ».</p>
                </Article>

                <Article n={8} title="Accès aux services">
                    <p>Les services sont accessibles dès la confirmation du paiement. Les rapports et avis de valeur sont générés à la demande et restent téléchargeables depuis « Mon compte » tant que le compte existe.</p>
                </Article>

                <Article n={9} title="Satisfait ou remboursé">
                    <p>Lors de sa première souscription, le Client peut demander le remboursement intégral de son premier paiement, sans avoir à se justifier, en écrivant à {LEGAL.email} dans les 14 jours qui suivent ce paiement. L'abonnement est alors résilié et l'accès aux services prend fin à la date du remboursement.</p>
                    <p>Cette garantie commerciale s'applique une seule fois par Client (même société ou même utilisateur), et ne s'applique pas aux renouvellements ni aux contrats Réseau, qui suivent leurs conditions particulières.</p>
                </Article>

                <Article n={10} title="Durée et résiliation">
                    <p>L'abonnement est conclu pour un mois ou un an selon la périodicité choisie, et renouvelé automatiquement pour la même durée. Les formules Solo et Agence sont sans engagement : le Client peut les résilier à tout moment depuis « Mon compte », rubrique « Factures et abonnement ». La résiliation prend effet à la fin de la période en cours, déjà payée, qui n'est pas remboursée, sauf application de l'article 9. Les contrats Réseau sont conclus pour 12 mois.</p>
                    <p>En cas d'échec du paiement, l'accès aux services est suspendu jusqu'à régularisation.</p>
                    <p>La suppression du compte par le Client entraîne la résiliation immédiate de l'abonnement, sans remboursement de la période en cours.</p>
                </Article>

                <Article n={11} title="Disponibilité et assistance">
                    <p>Le Vendeur met en œuvre les moyens raisonnables pour assurer l'accès aux services 24 heures sur 24, sous réserve des opérations de maintenance et de l'indisponibilité des sources de données publiques (ADEME, DVF, Base Adresse Nationale). Le Client peut signaler toute anomalie à {LEGAL.email} ; le Vendeur y répond dans les meilleurs délais.</p>
                </Article>

                <Article n={12} title="Responsabilité">
                    <p>Le Vendeur est tenu d'une obligation de moyens. Compte tenu de la nature indicative des résultats (article 4), sa responsabilité ne peut être engagée pour les décisions prises par le Client ou par ses propres clients sur leur seul fondement, ni pour un écart entre les estimations et les coûts, aides, consommations ou prix de vente réels.</p>
                    <p>La responsabilité du Vendeur est limitée aux dommages directs et prévisibles, dans la limite des sommes versées par le Client au cours des douze derniers mois. Le Client reste seul responsable des informations et documents qu'il remet à ses propres clients.</p>
                </Article>

                <Article n={13} title="Propriété intellectuelle et usage des rapports">
                    <p>Le site, ses contenus et ses méthodes de calcul sont la propriété du Vendeur. Le Client peut utiliser les rapports et avis de valeur pour les besoins de son activité et les remettre à ses propres clients pour le logement concerné. Toute revente de rapports, ou extraction systématique des résultats du site, est interdite.</p>
                </Article>

                <Article n={14} title="Carte de prospection">
                    <p><b>Contenu.</b> La carte de prospection affiche, pour une zone choisie par le Client, les adresses des logements dont le DPE est classé E, F ou G, avec les caractéristiques publiées dans ce DPE. Ces informations proviennent de la base des DPE publiée par l'ADEME sous Licence Ouverte 2.0 ; elles ne comprennent ni le nom ni les coordonnées des propriétaires ou des occupants. Le Vendeur ne les modifie pas et n'en garantit ni l'exactitude ni l'actualité : un logement peut avoir été rénové, vendu ou avoir fait l'objet d'un DPE plus récent non pris en compte.</p>
                    <p><b>Usage professionnel.</b> La carte est réservée à un usage professionnel, pour les besoins propres de l'activité du Client (recherche de mandats, proposition d'estimation, d'accompagnement ou de travaux). Le Client est seul responsable des traitements de données personnelles qu'il réalise à partir de ces informations, au sens du règlement général sur la protection des données (RGPD), et de leur conformité à la loi.</p>
                    <p><b>Engagements du Client.</b> Le Client s'engage notamment à :</p>
                    <ul className="list-disc pl-5 space-y-1">
                        <li>indiquer, dans toute prise de contact, l'origine des informations (données publiques des DPE de l'ADEME) et un moyen simple de s'opposer à tout nouveau contact, puis respecter sans délai les oppositions reçues ;</li>
                        <li>ne pas rapprocher ces informations d'autres fichiers ou sources dans le but d'identifier les propriétaires ou les occupants, sauf base légale dont il répond ;</li>
                        <li>ne pas utiliser ces informations pour un démarchage téléphonique, par SMS ou par email non sollicité, ni à des fins discriminatoires, de pression ou de dénigrement ;</li>
                        <li>ne conserver les adresses extraites que le temps nécessaire à sa campagne de prospection ;</li>
                        <li>ne pas revendre, publier ou mettre à disposition de tiers les listes obtenues, et ne pas procéder à une extraction systématique de la carte au-delà de ses besoins professionnels.</li>
                    </ul>
                    <p>Les rappels et le modèle de courrier proposés sur la carte sont fournis à titre d'aide ; ils ne constituent pas un conseil juridique et n'exonèrent pas le Client de ses obligations.</p>
                    <p><b>Courriers et pages de contact.</b> Le Client peut générer, pour un logement, un courrier comportant un lien et un QR code vers une page à son nom présentant une simulation de ce logement, sur laquelle le destinataire peut demander à être recontacté. Le Client est responsable du traitement des demandes ainsi recueillies ; le Vendeur les héberge et les met à sa disposition pour son compte, en qualité de sous-traitant au sens de l'article 28 du RGPD : il ne les utilise à aucune autre fin, en assure la sécurité et la confidentialité, et les supprime à la demande du Client, à la suppression de son compte ou au plus tard trois ans après leur recueil. Le Client s'engage à n'utiliser ces demandes que pour recontacter la personne au sujet du logement concerné, à répondre aux demandes d'exercice de droits qu'il reçoit et à exactement renseigner les coordonnées de son agence affichées sur la page.</p>
                    <p><b>Responsabilité et suspension.</b> Le Client garantit le Vendeur contre toute réclamation, action ou sanction résultant de l'usage qu'il fait de ces informations en méconnaissance du présent article ou de la réglementation. En cas d'usage manifestement contraire au présent article, notamment d'extraction massive ou de signalement fondé d'une personne démarchée, le Vendeur peut suspendre l'accès à la carte après en avoir informé le Client, sans préjudice des autres services de l'abonnement.</p>
                </Article>

                <Article n={15} title="Données personnelles">
                    <p>Le Vendeur traite l'adresse email du Client, les simulations enregistrées dans ses rapports et les informations de facturation pour fournir le service, facturer et respecter ses obligations comptables. Les paiements sont traités par Stripe, l'authentification et l'hébergement des données par Supabase. Les données sont conservées pendant la durée du compte, puis le temps des obligations légales (10 ans pour les pièces comptables).</p>
                    <p>Le Client dispose d'un droit d'accès, de rectification, d'effacement, de limitation, d'opposition et de portabilité, qu'il exerce à {LEGAL.email}. Il peut introduire une réclamation auprès de la CNIL. Le détail figure dans la <Link to="/confidentialite" className="underline text-brass hover:text-brass-light">politique de confidentialité</Link>.</p>
                </Article>

                <Article n={16} title="Réclamations">
                    <p>Toute réclamation est adressée à {LEGAL.email}. Les parties s'efforcent de régler à l'amiable tout différend avant de saisir la juridiction compétente.</p>
                </Article>

                <Article n={17} title="Droit applicable et juridiction">
                    <p>Les présentes CGV sont soumises au droit français. Compétence exclusive est attribuée au {LEGAL.court}, y compris en cas de pluralité de défendeurs ou d'appel en garantie.</p>
                </Article>

        </LegalPage>
    );
}
