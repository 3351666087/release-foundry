import type { Config } from "tailwindcss";

const config = {
  content: [
    "./apps/dashboard/index.html",
    "./apps/dashboard/src/**/*.{js,mjs,jsx,ts,tsx,html}",
    "./services/report/**/*.{js,mjs,ts,tsx}",
    "./tests/a3/**/*.{js,mjs,ts,tsx}",
    "./tests/e2e/**/*.{js,mjs,ts,tsx}",
    "./docs/a3/**/*.{md,mdx,html}",
    "./fixtures/a3/**/*.{json,md,html}"
  ],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: "#f7f8f4",
          muted: "#eef1ea",
          inverse: "#151814"
        },
        surface: {
          DEFAULT: "#ffffff",
          raised: "#fbfcf8",
          inset: "#edf2ef"
        },
        ink: {
          DEFAULT: "#18201d",
          muted: "#59635e",
          subtle: "#7c8781",
          inverse: "#f6f7f3"
        },
        line: {
          DEFAULT: "#d8ded8",
          strong: "#aeb8b0"
        },
        accent: {
          DEFAULT: "#147d74",
          soft: "#d9f0eb",
          strong: "#0d5e57"
        },
        evidence: {
          DEFAULT: "#2c6fbb",
          soft: "#dceafa",
          strong: "#174f8f"
        },
        success: {
          DEFAULT: "#2f7d4f",
          soft: "#ddf1e4",
          strong: "#1f5d39"
        },
        warning: {
          DEFAULT: "#b56a09",
          soft: "#fde8c3",
          strong: "#814904"
        },
        danger: {
          DEFAULT: "#b7354a",
          soft: "#f8dce2",
          strong: "#872234"
        },
        review: {
          DEFAULT: "#6f5a12",
          soft: "#f3e9bf",
          strong: "#51400b"
        }
      },
      spacing: {
        "a3-field": "0.625rem",
        "a3-row": "0.875rem",
        "a3-panel": "1rem",
        "a3-section": "1.5rem",
        "a3-gutter": "2rem",
        "a3-rail": "3rem",
        "a3-touch": "2.75rem"
      },
      borderRadius: {
        control: "0.375rem",
        card: "0.5rem",
        panel: "0.5rem",
        modal: "0.625rem"
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "Arial",
          "sans-serif"
        ],
        mono: [
          "JetBrains Mono",
          "SFMono-Regular",
          "Consolas",
          "Liberation Mono",
          "monospace"
        ]
      },
      fontSize: {
        "a3-caption": ["0.75rem", { lineHeight: "1rem", fontWeight: "500" }],
        "a3-body": ["0.875rem", { lineHeight: "1.375rem", fontWeight: "450" }],
        "a3-label": ["0.8125rem", { lineHeight: "1rem", fontWeight: "650" }],
        "a3-title": ["1rem", { lineHeight: "1.375rem", fontWeight: "700" }],
        "a3-metric": ["1.5rem", { lineHeight: "2rem", fontWeight: "750" }]
      },
      boxShadow: {
        panel: "0 1px 2px rgb(24 32 29 / 0.08), 0 8px 24px rgb(24 32 29 / 0.06)",
        focus: "0 0 0 3px rgb(20 125 116 / 0.24)"
      }
    }
  },
  plugins: []
} satisfies Config;

export default config;
