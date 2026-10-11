import { LEGAL } from '../legal';
import { Link } from '../router';
import { LegalPage, LegalSection } from './site';

export default function MentionsLegalesPage() {
    return (
        <LegalPage title="Mentions légales" description="Éditeur, hébergeur, propriété intellectuelle et sources des données publiques réutilisées par SPREA.">
            <LegalSection title="Éditeur du site">
                <p>
                    {LEGAL.companyName}, {LEGAL.legalForm}<br />
                    Siège social : {LEGAL.address}<br />
                    {LEGAL.registration}<br />
                    {LEGAL.vat}<br />
                    Téléphone : {LEGAL.phone}<br />
                    Email : {LEGAL.email}
                </p>
                <p>Directeur de la publication : {LEGAL.publicationDirector}</p>
            </LegalSection>

            <LegalSection title="Hébergement">
                <p>
                    Site et API : {LEGAL.hostName}, {LEGAL.hostAddress} – {LEGAL.hostWebsite}<br />
                    Base de données des comptes : Supabase, région {LEGAL.databaseRegion} – https://supabase.com
                </p>
            </LegalSection>

            <LegalSection title="Données utilisées">
                <p>Le site réutilise, sous Licence Ouverte 2.0 (Etalab) : la base des diagnostics de performance énergétique et l'annuaire des entreprises RGE (ADEME), la Base Adresse Nationale, les demandes de valeurs foncières DVF (DGFiP, Etalab), la Base de données nationale des bâtiments (CSTB), les fichiers des locaux des personnes morales (DGFiP), le registre national des copropriétés (Anah), le BODACC (DILA) et les fonds de carte de l'IGN ; ainsi que l'Annuaire des entreprises (DINUM). Ces données sont lues à leur dernière mise à jour publiée ; la date des ventes et des DPE utilisés est indiquée dans les rapports. Les estimations produites par le site sont indicatives et n'engagent ni ces producteurs de données, ni l'État.</p>
            </LegalSection>

            <LegalSection title="Propriété intellectuelle">
                <p>Les contenus du site (textes, interface, méthodes de calcul, rapports) sont protégés. Toute reproduction ou extraction systématique sans autorisation de l'éditeur est interdite, sous réserve des droits d'usage des rapports prévus par les <Link to="/cgv" className="underline text-brass hover:text-brass-light">conditions générales de vente</Link>.</p>
            </LegalSection>

            <LegalSection title="Données personnelles">
                <p>Le traitement des données personnelles est décrit dans la <Link to="/confidentialite" className="underline text-brass hover:text-brass-light">politique de confidentialité</Link>.</p>
            </LegalSection>
        </LegalPage>
    );
}
