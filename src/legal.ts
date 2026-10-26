// Legal information shown in the CGV and the footer.
// Every value in [brackets] must be replaced before selling: a banner is shown
// on the legal pages while some are missing.

export const CGV_VERSION = '2026-10-10.3'; // Keep in sync with TERMS_VERSION in api/accounts.py

export const LEGAL = {
    brand: 'SPREA',
    companyName: 'Tarik Lakel EI',
    legalForm: 'entrepreneur individuel, nom commercial SPREA',
    address: '239b rue du Jardin des Plantes, 59000 Lille',
    registration: '[SIREN / RCS, ex. RCS Lille 123 456 789]',
    // e.g. "TVA intracommunautaire : FR12345678901" or "TVA non applicable, art. 293 B du CGI"
    vat: '[Numéro de TVA intracommunautaire ou mention de franchise en base]',
    email: 'contact@sprea.app',
    // Court competent for disputes (customers are professionals only)
    court: '[Tribunal de commerce de ...]',
    phone: '[Numéro de téléphone]',
    publicationDirector: 'Tarik Lakel',
    // Hosting provider (LCEN art. 6): check the current address on vercel.com/legal
    hostName: 'Vercel Inc.',
    hostAddress: '440 N Barranca Ave #4133, Covina, CA 91723, États-Unis',
    hostWebsite: 'https://vercel.com',
    // Region chosen for the Supabase project (accounts database)
    databaseRegion: "Union européenne (Paris)",
};

export const isLegalIncomplete = () => Object.values(LEGAL).some(v => v.startsWith('['));
