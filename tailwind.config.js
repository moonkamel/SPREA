/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            // Dark, sober "advisory firm" palette. DPE label colours stay the official ones (src/ui.tsx).
            colors: {
                canvas: '#0A0F1A',   // page background
                panel: '#111A2B',    // cards
                raised: '#18233A',   // inputs, nested blocks
                line: '#25324C',     // borders, separators
                ink: { DEFAULT: '#ECEFF4', soft: '#C5CCD8' }, // main text
                muted: '#97A1B3',    // secondary text
                faint: '#6C778C',    // hints
                brass: { DEFAULT: '#C9A45C', light: '#E3C98F', dark: '#A8853F' }, // accent
                sage: '#6FBF8E',     // positive amounts
                coral: '#E2775E',    // warnings
            },
            fontFamily: {
                sans: ['"Inter Variable"', 'system-ui', 'sans-serif'],
                serif: ['"Source Serif 4 Variable"', 'Georgia', 'serif'],
            },
        },
    },
    plugins: [],
}
