import { LEGAL } from '../legal';
import { Link } from '../router';
import { LegalPage, LegalSection } from './site';

export default function MentionsLegalesPage() {
    return (
        <LegalPage title="Mentions légales">
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
                <p>Les informations sur les logements proviennent des données publiques des diagnostics de performance énergétique publiées par l'ADEME (data.ademe.fr) et de la Base Adresse Nationale (adresse.data.gouv.fr), sous Licence Ouverte. Les estimations produites par le site sont indicatives et n'engagent ni l'ADEME, ni l'État.</p>
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
