import type { ReactNode } from 'react';
import { CGV_VERSION, LEGAL } from '../legal';
import { Link } from '../router';
import { LegalPage, LegalSection } from './site';

function Article({ n, title, children }: { n: number; title: string; children: ReactNode }) {
    return <LegalSection title={`Article ${n} – ${title}`}>{children}</LegalSection>;
}

export default function CgvPage() {
    const version = new Date(CGV_VERSION).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    return (
        <LegalPage title="Conditions générales de vente" updated={`Version du ${version}`}>

                <Article n={1} title="Objet et champ d'application">
                    <p>Les présentes conditions générales de vente (« CGV ») régissent les ventes conclues sur le site {LEGAL.brand} entre {LEGAL.companyName} (« le Vendeur ») et toute personne, consommateur ou professionnel, achetant un rapport ou souscrivant un abonnement (« le Client »).</p>
                    <p>Le Client les accepte expressément avant chaque achat en cochant la case prévue à cet effet. Les CGV applicables sont celles en vigueur à la date de la commande.</p>
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
                    <p><b>Simulation gratuite.</b> À partir des données publiques du diagnostic de performance énergétique (DPE) publiées par l'ADEME, le site estime les travaux de rénovation envisageables, leur coût, l'étiquette énergétique après travaux, les aides mobilisables, le reste à charge et les économies d'énergie. La simulation est accessible sans compte et sans paiement.</p>
                    <p><b>Rapport.</b> Document PDF reprenant la simulation d'un logement, accompagné d'une analyse rédigée. Il est vendu à l'unité.</p>
                    <p><b>Abonnement Pro.</b> Abonnement mensuel donnant accès à un nombre illimité de rapports pendant sa durée. Il s'adresse principalement aux professionnels de l'immobilier et de la rénovation.</p>
                    <p>Les caractéristiques essentielles de chaque offre sont présentées sur la page <Link to="/tarifs" className="underline text-blue-600">Tarifs</Link> et rappelées avant le paiement.</p>
                </Article>

                <Article n={4} title="Nature des résultats">
                    <p>Les simulations et rapports sont des <b>estimations indicatives</b>, établies à partir des données publiques du DPE, de valeurs moyennes de construction et de coûts moyens de marché. Ils ne constituent ni un DPE, ni un audit énergétique réglementaire, ni un devis, ni une étude thermique, ni un conseil juridique, fiscal ou financier.</p>
                    <p>Les montants d'aides sont calculés selon les barèmes publics connus à la date de la simulation. Leur attribution dépend de conditions d'éligibilité vérifiées par les organismes compétents (Anah, fournisseurs d'énergie, banques) et doit être confirmée par France Rénov' ou un Accompagnateur Rénov' avant tout engagement. Les résultats dépendent de l'exactitude des données du DPE, dont le Vendeur n'est pas l'auteur.</p>
                </Article>

                <Article n={5} title="Compte client">
                    <p>L'achat d'un rapport ou d'un abonnement nécessite un compte, créé à partir d'une adresse email. La connexion s'effectue par un lien envoyé à cette adresse. Le Client est responsable de l'accès à sa messagerie et de l'exactitude de son adresse email. Il peut supprimer son compte à tout moment depuis l'espace « Mon compte » ; ses rapports ne sont alors plus accessibles.</p>
                </Article>

                <Article n={6} title="Prix">
                    <p>Les prix sont indiqués en euros, toutes taxes comprises, sur la page Tarifs et avant le paiement. Le prix applicable est celui affiché au moment de la commande.</p>
                    <p>Le Vendeur peut modifier le prix de l'abonnement Pro. Le Client en est informé par email au moins 30 jours avant son application ; le nouveau prix s'applique à la période suivante, et le Client peut résilier sans frais avant cette date.</p>
                </Article>

                <Article n={7} title="Commande et paiement">
                    <p>La commande est passée depuis le site : choix du rapport ou de l'abonnement, acceptation des CGV, puis paiement par carte bancaire sur la page sécurisée de notre prestataire de paiement Stripe. Le Vendeur n'a pas accès aux données de carte bancaire.</p>
                    <p>La vente est conclue à la confirmation du paiement. Une facture est émise et mise à disposition du Client. L'abonnement Pro est prélevé chaque mois à la date anniversaire de la souscription.</p>
                </Article>

                <Article n={8} title="Mise à disposition">
                    <p>Le rapport est mis à disposition immédiatement après la confirmation du paiement, par téléchargement. Il reste téléchargeable depuis l'espace « Mon compte » tant que le compte existe. Pour les abonnés Pro, chaque rapport est disponible immédiatement.</p>
                </Article>

                <Article n={9} title="Droit de rétractation (consommateurs)">
                    <p><b>Rapport.</b> Conformément à l'article L221-28 13° du Code de la consommation, le droit de rétractation ne peut être exercé pour un contenu numérique fourni sans support matériel dont l'exécution a commencé avec l'accord préalable exprès du consommateur, qui a reconnu perdre son droit de rétractation. Avant le paiement, le Client demande expressément l'accès immédiat à son rapport et reconnaît perdre ce droit dès sa mise à disposition.</p>
                    <p><b>Abonnement Pro.</b> Le consommateur dispose d'un délai de 14 jours à compter de la souscription pour se rétracter, sans motif. En demandant le démarrage immédiat de l'abonnement, il accepte, en cas de rétractation, de payer un montant proportionnel au service fourni jusqu'à la communication de sa décision (article L221-25 du Code de la consommation). Le droit de rétractation ne peut plus être exercé si le service a été pleinement exécuté avant la fin de ce délai.</p>
                    <p>Pour se rétracter, le Client adresse une déclaration dénuée d'ambiguïté à {LEGAL.email}, par exemple au moyen du formulaire figurant en annexe. Le remboursement intervient dans les 14 jours, par le même moyen de paiement.</p>
                    <p>Le droit de rétractation ne s'applique pas aux Clients professionnels.</p>
                </Article>

                <Article n={10} title="Durée et résiliation de l'abonnement Pro">
                    <p>L'abonnement est conclu pour une durée d'un mois, renouvelée automatiquement. Il est sans engagement : le Client peut le résilier à tout moment depuis « Mon compte », rubrique « Factures et abonnement ». La résiliation prend effet à la fin de la période en cours, déjà payée, qui n'est pas remboursée. Les rapports obtenus restent téléchargeables.</p>
                    <p>En cas d'échec du paiement, l'accès aux nouveaux rapports est suspendu jusqu'à régularisation.</p>
                    <p>La suppression du compte par le Client entraîne la résiliation immédiate de l'abonnement, sans remboursement de la période en cours.</p>
                </Article>

                <Article n={11} title="Garanties légales">
                    <p>Le consommateur bénéficie de la garantie légale de conformité des contenus et services numériques prévue aux articles L224-25-12 et suivants du Code de la consommation. En cas de défaut de conformité (rapport illisible, incomplet ou ne correspondant pas à la simulation commandée), il contacte le Vendeur, qui procède à la mise en conformité ou, à défaut, au remboursement.</p>
                </Article>

                <Article n={12} title="Responsabilité">
                    <p>Le Vendeur est tenu d'une obligation de moyens. Compte tenu de la nature indicative des résultats (article 4), sa responsabilité ne peut être engagée pour les décisions prises par le Client ou par des tiers sur leur seul fondement, ni pour un écart entre les estimations et les coûts, aides ou consommations réels.</p>
                    <p>Vis-à-vis des Clients professionnels, la responsabilité du Vendeur est limitée aux dommages directs et prévisibles, dans la limite des sommes versées par le Client au cours des douze derniers mois. Aucune limitation ne s'applique aux consommateurs au-delà de ce que permet la loi.</p>
                    <p>Le service peut être interrompu pour maintenance ou en cas d'indisponibilité des données publiques (ADEME, Base Adresse Nationale).</p>
                </Article>

                <Article n={13} title="Propriété intellectuelle et usage des rapports">
                    <p>Le site, ses contenus et ses méthodes de calcul sont la propriété du Vendeur. Le Client peut utiliser les rapports pour ses besoins personnels ou professionnels ; un Client professionnel peut les remettre à ses propres clients pour le logement concerné. Toute revente de rapports, ou extraction systématique des résultats du site, est interdite.</p>
                </Article>

                <Article n={14} title="Données personnelles">
                    <p>Le Vendeur traite l'adresse email du Client, les simulations enregistrées dans ses rapports et les informations de facturation pour fournir le service, facturer et respecter ses obligations comptables. Les paiements sont traités par Stripe, l'authentification et l'hébergement des données par Supabase. Les données sont conservées pendant la durée du compte, puis le temps des obligations légales (10 ans pour les pièces comptables).</p>
                    <p>Le Client dispose d'un droit d'accès, de rectification, d'effacement, de limitation, d'opposition et de portabilité, qu'il exerce à {LEGAL.email}. Il peut introduire une réclamation auprès de la CNIL. Le détail figure dans la <Link to="/confidentialite" className="underline text-blue-600">politique de confidentialité</Link>.</p>
                </Article>

                <Article n={15} title="Réclamations et médiation">
                    <p>Toute réclamation est adressée à {LEGAL.email}. En cas de litige non résolu, le consommateur peut recourir gratuitement au médiateur de la consommation : {LEGAL.mediatorName} ({LEGAL.mediatorUrl}), après avoir tenté de résoudre le litige directement auprès du Vendeur par une réclamation écrite.</p>
                </Article>

                <Article n={16} title="Droit applicable et juridiction">
                    <p>Les présentes CGV sont soumises au droit français. Pour les consommateurs, les litiges relèvent des juridictions désignées par les règles légales. Pour les Clients professionnels, compétence exclusive est attribuée au {LEGAL.court}.</p>
                </Article>

                <section className="space-y-3 border-t border-slate-100 pt-8">
                    <h2 className="text-lg font-black text-slate-800 tracking-tight">Annexe – Formulaire de rétractation</h2>
                    <p className="text-xs text-slate-400">À compléter et renvoyer uniquement si vous souhaitez vous rétracter du contrat.</p>
                    <div className="text-sm text-slate-600 leading-relaxed bg-slate-50 rounded-2xl p-5 space-y-2">
                        <p>À l'attention de {LEGAL.companyName}, {LEGAL.address}, {LEGAL.email} :</p>
                        <p>Je vous notifie par la présente ma rétractation du contrat portant sur la prestation de services ci-dessous :</p>
                        <p>Commandé le : …………… · Nom du consommateur : …………… · Adresse email du compte : ……………</p>
                        <p>Date : …………… · Signature (uniquement en cas de notification sur papier)</p>
                    </div>
                </section>
        </LegalPage>
    );
}
