/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#2563eb',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f7f8fa',
          hover: '#f0f2f5',
        },
        text: {
          primary: '#1a1a2e',
          secondary: '#6b7280',
          tertiary: '#9ca3af',
        },
      },
      maxWidth: {
        'chat': '780px',
      },
      borderRadius: {
        'chat': '16px',
        'bubble': '18px',
        'input': '24px',
      },
      boxShadow: {
        'chat': '0 2px 12px rgba(0, 0, 0, 0.04)',
        'input': '0 2px 8px rgba(0, 0, 0, 0.06)',
        'card': '0 1px 4px rgba(0, 0, 0, 0.04)',
        'card-hover': '0 4px 12px rgba(37, 99, 235, 0.1)',
      },
    },
  },
  plugins: [],
}
