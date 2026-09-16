/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4fc",
          100: "#d6e6f7",
          200: "#adccef",
          300: "#7fb0e5",
          400: "#4f92d9",
          500: "#3277c2",
          600: "#265d9c",
          700: "#1f4a7c",
          800: "#1a3c63",
          900: "#173252",
        },
      },
    },
  },
  plugins: [],
};
