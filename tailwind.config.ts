import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#F7F6F2",
        surface: {
          DEFAULT: "#FFFFFF",
          raised: "#FFFFFF",
          hover: "#F4F2EC",
          subtle: "#FAF9F5",
        },
        border: {
          DEFAULT: "#E7E5DE",
          subtle: "#EFECE5",
          strong: "#D8D4CA",
        },
        foreground: {
          DEFAULT: "#252923",
          muted: "#74766F",
          subtle: "#9B9C94",
        },
        accent: {
          forest: "#536B56",
          "forest-subtle": "#E9EEE7",
          "forest-border": "rgba(83, 107, 86, 0.22)",
          terracotta: "#B97857",
          "terracotta-subtle": "#F9EFEB",
          "terracotta-border": "rgba(185, 120, 87, 0.24)",
          // Aliases for compatibility
          cyan: "#536B56",
          "cyan-subtle": "#E9EEE7",
          "cyan-border": "rgba(83, 107, 86, 0.22)",
        },
        status: {
          critical: "#B64A38",
          "critical-bg": "#FBF1EE",
          "critical-border": "#EED2CB",
          warning: "#C58528",
          "warning-bg": "#FBF6ED",
          "warning-border": "#EFE3CF",
          healthy: "#536B56",
          "healthy-bg": "#E9EEE7",
          "healthy-border": "#CCD7CC",
          neutral: "#74766F",
          "neutral-bg": "#F3F1EC",
          "neutral-border": "#E2DFD6",
        },
        sidebar: {
          DEFAULT: "#FAF9F5",
          border: "#E7E5DE",
          active: "#EFECE5",
          foreground: "#252923",
          muted: "#74766F",
        },
      },
      borderRadius: {
        sm: "4px",
        md: "6px",
        lg: "8px",
        xl: "10px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
