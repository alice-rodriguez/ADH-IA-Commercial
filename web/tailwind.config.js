/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        adh: {
          black: '#000000',
          white: '#FFFFFF',
          orange: '#ff914d',
          violet: '#d6a9cf',
        },
      },
    },
  },
  plugins: [],
}

