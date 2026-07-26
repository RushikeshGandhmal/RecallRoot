import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#080A0F",
          900: "#0D1119",
          850: "#111722",
          800: "#161D2A",
          700: "#232D3D",
        },
        signal: {
          300: "#B6FFDC",
          400: "#7EF2BC",
          500: "#45DB9C",
          600: "#24B97F",
        },
        danger: {
          300: "#FFB6B9",
          400: "#FF858C",
          500: "#F45B69",
          600: "#D83E50",
        },
        amber: {
          300: "#FFE0A3",
          400: "#FFC766",
          500: "#EFA83F",
        },
      },
      boxShadow: {
        panel: "0 24px 80px rgba(0, 0, 0, 0.28)",
        glow: "0 0 0 1px rgba(126, 242, 188, 0.12), 0 20px 55px rgba(20, 150, 100, 0.08)",
      },
      animation: {
        "pulse-soft": "pulseSoft 2.4s ease-in-out infinite",
        "scan": "scan 2.8s linear infinite",
        "fade-up": "fadeUp 420ms ease-out both",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "0.55", transform: "scale(0.92)" },
          "50%": { opacity: "1", transform: "scale(1.08)" },
        },
        scan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        fadeUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
