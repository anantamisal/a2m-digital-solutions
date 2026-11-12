/**
 * Tailwind build config.
 *
 * This is the exact config that used to live inline in index.html and
 * admin.html (`tailwind.config = {...}`). It is now a real file so Tailwind
 * can be compiled to a static stylesheet at build time instead of shipping
 * the 400 KB Tailwind Play CDN script to every visitor.
 *
 * Rebuild with:  npm run build:css      (see package.json)
 */
module.exports = {
    darkMode: 'class',
    content: [
        './index.html',
        './admin.html',
        './script.js',
    ],
    theme: {
        extend: {
            colors: {
                brand: {
                    50: '#f0f3ff',
                    100: '#e1e7ff',
                    500: '#6366f1',
                    600: '#4f46e5',
                    700: '#4338ca',
                    cyan: '#06b6d4',
                    purple: '#a855f7',
                    pink: '#ec4899',
                    dark: '#090d16',
                    card: 'rgba(15, 23, 42, 0.75)',
                    border: 'rgba(255, 255, 255, 0.08)'
                }
            },
            fontFamily: {
                sans: ['"Plus Jakarta Sans"', 'sans-serif'],
                mono: ['"JetBrains Mono"', 'monospace']
            },
            animation: {
                'pulse-glow': 'pulseGlow 4s infinite alternate',
                'float': 'float 6s ease-in-out infinite',
                'float-delayed': 'float 6s ease-in-out 3s infinite',
                'gradient-x': 'gradientX 8s ease infinite'
            },
            keyframes: {
                pulseGlow: {
                    '0%': { opacity: '0.3', transform: 'scale(1)' },
                    '100%': { opacity: '0.7', transform: 'scale(1.08)' }
                },
                float: {
                    '0%, 100%': { transform: 'translateY(0px)' },
                    '50%': { transform: 'translateY(-12px)' }
                },
                gradientX: {
                    '0%, 100%': { 'background-size': '200% 200%', 'background-position': 'left center' },
                    '50%': { 'background-size': '200% 200%', 'background-position': 'right center' }
                }
            }
        }
    }
};
