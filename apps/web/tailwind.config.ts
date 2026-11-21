import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#FAFAF7",
        surface: "#FFFFFF",
        text: "#1A1A1A",
        muted: "#6B7280",
        border: "#E5E7EB",
        primary: { DEFAULT: "#1F4D2B", fg: "#FFFFFF" },
        secondary: { DEFAULT: "#97BC62", fg: "#1A1A1A" },
        accent: { DEFAULT: "#F2A900", fg: "#1A1A1A" },
        danger: { DEFAULT: "#C0392B", fg: "#FFFFFF" },
      },
      fontFamily: {
        sans: ["var(--font-noto)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
