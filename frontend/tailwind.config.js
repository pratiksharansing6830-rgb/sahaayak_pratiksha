/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#effaf8",
          100: "#d7f2ee",
          500: "#14917f",
          600: "#0f7567",
          700: "#0e5d53",
        },
        warm: { 50: "#fbf8f3", 100: "#f4eee4" },
      },
    },
  },
  plugins: [],
};