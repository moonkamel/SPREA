// Legal information shown in the CGV and the footer.
// Every value in [brackets] must be replaced before selling: a banner is shown
// on the legal pages while some are missing.

export const CGV_VERSION = '2026-10-10.1'; // Keep in sync with TERMS_VERSION in api/accounts.py

export const LEGAL = {
    brand: 'SPREA',
    companyName: '[Raison sociale]',
    legalForm: '[Forme juridique et capital, ex. SAS au capital de 1 000 €]',
    address: '[Adresse du siège social]',
    registration: '[SIREN / RCS, ex. RCS Lille 123 456 789]',
    // e.g. "TVA intracommunautaire : FR12345678901" or "TVA non applicable, art. 293 B du CGI"
    vat: '[Numéro de TVA intracommunautaire ou mention de franchise en base]',
    email: '[contact@votre-domaine.fr]',
    // Court competent for disputes (customers are professionals only)
    court: '[Tribunal de commerce de ...]',
    phone: '[Numéro de téléphone]',
    publicationDirector: '[Nom du directeur de la publication]',
    // Hosting provider (LCEN art. 6): check the current address on vercel.com/legal
    hostName: 'Vercel Inc.',
    hostAddress: '440 N Barranca Ave #4133, Covina, CA 91723, États-Unis',
    hostWebsite: 'https://vercel.com',
    // Region chosen for the Supabase project (accounts database)
    databaseRegion: "[Région du projet Supabase, ex. Union européenne (Francfort)]",
};

export const isLegalIncomplete = () => Object.values(LEGAL).some(v => v.startsWith('['));
