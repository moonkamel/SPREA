import { useEffect } from 'react';

// Page metadata kept in sync on client-side navigation. The same values are
// written into the prerendered HTML of each public page (scripts/seo/prerender.mjs).

export const SITE_NAME = 'SPREA';

const setMeta = (attr: 'name' | 'property', key: string, value: string) => {
    let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
    if (!el) {
        el = document.createElement('meta');
        el.setAttribute(attr, key);
        document.head.appendChild(el);
    }
    el.setAttribute('content', value);
};

export function useSeo({ title, description, path, noindex = false }: {
    title: string;
    description?: string;
    path?: string;
    noindex?: boolean;
}) {
    useEffect(() => {
        document.title = title;
        setMeta('property', 'og:title', title);
        if (description) {
            setMeta('name', 'description', description);
            setMeta('property', 'og:description', description);
        }
        setMeta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow');
        if (path !== undefined) {
            const url = `${window.location.origin}${path}`;
            let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
            if (!link) {
                link = document.createElement('link');
                link.rel = 'canonical';
                document.head.appendChild(link);
            }
            link.href = url;
            setMeta('property', 'og:url', url);
        }
    }, [title, description, path, noindex]);
}

// "Côtes-d'Armor", "22" -> "cotes-d-armor-22" (same rule in scripts/seo/prerender.mjs)
export const departmentSlug = (name: string, code: string) =>
    `${name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${code.toLowerCase()}`;
