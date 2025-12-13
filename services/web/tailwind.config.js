/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{astro,html,js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sora: ['Sora', 'Inter', 'SF Pro Display', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
