import type { Config } from "tailwindcss";

export default {
  "darkMode": "class",
  "content": [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  "theme": {
    "extend": {
      "colors": {
        "background": "#F8F6F0",
        "foreground": "#302D28",
        "primary": {
          "DEFAULT": "#96472F",
          "foreground": "#FCFAF5"
        },
        "primaryForeground": "#FCFAF5",
        "secondary": "#EAE4D8",
        "muted": {
          "DEFAULT": "#F0EBE1",
          "foreground": "#696154"
        },
        "mutedForeground": "#696154",
        "border": "#D9D1C3",
        "accent": "#716344"
      },
      "fontFamily": {
        "sans": "\"Avenir Next\", \"PingFang SC\", system-ui, sans-serif",
        "mono": "\"SFMono-Regular\", Consolas, monospace"
      },
      "fontSize": {
        "xs": "12.8px",
        "base": "16px",
        "lg": "20px",
        "xl": "25px",
        "2xl": "31.25px",
        "3xl": "39.06px",
        "4xl": "48.83px"
      },
      "borderRadius": {
        "lg": "12px",
        "md": "max(0px, calc(12px - 2px))",
        "sm": "max(0px, calc(12px - 4px))"
      },
      "spacing": {
        "container": "32px"
      },
      "boxShadow": {
        "card": "0 6px 24px rgb(48 45 40 / 0.04)",
        "popover": "0 16px 48px rgb(48 45 40 / 0.12)"
      }
    }
  },
  "plugins": []
} satisfies Config;
