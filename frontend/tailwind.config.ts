import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // AQI-band colors, wired to real thresholds when the dashboard
        // (Step 7) reads live/forecast data.
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
