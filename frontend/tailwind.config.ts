import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        layer: {
          core: "#3b82f6",
          jargon: "#f97316",
          prereq: "#a855f7",
        },
      },
      boxShadow: {
        glow: "0 0 0 3px rgba(59,130,246,.35), 0 10px 30px -10px rgba(0,0,0,.4)",
      },
      keyframes: {
        pulseRing: { "0%,100%": { boxShadow: "0 0 0 0 rgba(249,115,22,.5)" }, "50%": { boxShadow: "0 0 0 8px rgba(249,115,22,0)" } },
        fadeIn: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { pulseRing: "pulseRing 1.6s ease-out infinite", fadeIn: "fadeIn .18s ease-out" },
    },
  },
  plugins: [],
};
export default config;
