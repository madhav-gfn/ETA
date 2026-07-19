import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Noto Sans"', "system-ui", "sans-serif"],
      },
      colors: {
        // UX4G design-system tokens (ux4g-web-components :root variables).
        gov: {
          50: "#f2efff",
          100: "#dcd4ff",
          200: "#c0b3ff",
          300: "#a391ff",
          400: "#8670ff",
          500: "#6a4eff",
          600: "#4a2bc2",
          700: "#3d239f",
          800: "#301c7d",
          900: "#24145c",
        },
        saffron: {
          50: "#fff5ea",
          100: "#ffebd6",
          200: "#ffd9af",
          300: "#ffbe6f",
          400: "#e89c30",
          500: "#c47d00",
          600: "#a46800",
          700: "#764a00",
        },
        aqi: {
          good: "#4ade80",
          moderate: "#facc15",
          poor: "#fb923c",
          veryPoor: "#f87171",
          severe: "#a78bfa",
        },
      },
    },
  },
  plugins: [],
};

export default config;
