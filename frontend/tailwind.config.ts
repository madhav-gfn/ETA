import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(134,112,255,0.15), 0 8px 30px -8px rgba(106,78,255,0.35)",
      },
      colors: {
        // Dark, cool-slate scale authored for this theme: 50 = darkest surface,
        // 900 = near-white foreground. Every component in the app was written
        // against a conventional light-mode neutral scale (bg-neutral-50 for
        // page background, text-neutral-900 for primary text, etc.) — running
        // the numbers dark-to-light here flips the whole app to a dark theme
        // without having to touch every className.
        neutral: {
          50: "#07070b",
          100: "#0e0e15",
          200: "#1c1c27",
          300: "#2c2c3a",
          400: "#6c6c80",
          500: "#8b8b9e",
          600: "#a9a9ba",
          700: "#c5c5d3",
          800: "#dddde6",
          900: "#f6f6f9",
        },
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
