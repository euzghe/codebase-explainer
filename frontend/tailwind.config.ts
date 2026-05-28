import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b0d10",
        panel: "#13171c",
        border: "#252a31",
        ink: "#e7ebf0",
        muted: "#8a93a0",
        accent: "#7c9cf1",
        ok: "#5cd28a",
        warn: "#f0b85c",
        err: "#f06c6c",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
