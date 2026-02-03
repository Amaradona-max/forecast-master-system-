import type { Config } from "tailwindcss"

export default {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        pastel: {
          pink: {
            DEFAULT: "#FFD6E8",
            dark: "#FFB4D6",
            light: "#FFF0F7"
          },
          blue: {
            DEFAULT: "#C8E4FF",
            dark: "#A8D4FF",
            light: "#E8F4FF"
          },
          lavender: {
            DEFAULT: "#E5DEFF",
            dark: "#D4C5FF",
            light: "#F5F0FF"
          },
          mint: {
            DEFAULT: "#C8F4E8",
            dark: "#A8E8D4",
            light: "#E8FFF8"
          },
          peach: {
            DEFAULT: "#FFE4D6",
            dark: "#FFD4B8",
            light: "#FFF4ED"
          },
          lemon: {
            DEFAULT: "#FFF9D6",
            dark: "#FFEFB8",
            light: "#FFFEF0"
          }
        },
        accent: {
          coral: "#FF6B9D",
          blue: "#4D96FF",
          purple: "#9D6BFF",
          emerald: "#10B981",
          orange: "#FF8C42"
        },
        neutral: {
          50: "#FAFAFA",
          100: "#F5F5F5",
          200: "#EEEEEE",
          300: "#E0E0E0",
          400: "#BDBDBD",
          500: "#9E9E9E",
          600: "#757575",
          700: "#616161",
          800: "#424242",
          900: "#212121"
        },
        dark: {
          bg: "#1A1A2E",
          surface: "#25274D",
          border: "#3A3D5C",
          text: {
            primary: "#F5F5F5",
            secondary: "#BDBDBD"
          }
        }
      },
      fontFamily: {
        sans: [
          "Inter Variable",
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "SF Pro Display",
          "sans-serif"
        ],
        display: [
          "Cal Sans",
          "Inter Variable",
          "Inter",
          "system-ui",
          "sans-serif"
        ]
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.25" }],
        sm: ["0.875rem", { lineHeight: "1.5" }],
        base: ["1rem", { lineHeight: "1.5" }],
        lg: ["1.125rem", { lineHeight: "1.5" }],
        xl: ["1.25rem", { lineHeight: "1.5" }],
        "2xl": ["1.5rem", { lineHeight: "1.25" }],
        "3xl": ["1.875rem", { lineHeight: "1.25" }],
        "4xl": ["2.25rem", { lineHeight: "1.25" }]
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem",
        "26": "6.5rem",
        "30": "7.5rem"
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem"
      },
      boxShadow: {
        soft: "0 2px 15px -3px rgba(0, 0, 0, 0.07), 0 10px 20px -2px rgba(0, 0, 0, 0.04)",
        medium: "0 4px 20px -2px rgba(0, 0, 0, 0.1), 0 12px 28px -4px rgba(0, 0, 0, 0.08)",
        strong: "0 10px 40px -3px rgba(0, 0, 0, 0.15), 0 20px 50px -8px rgba(0, 0, 0, 0.12)",
        glass: "0 8px 32px 0 rgba(31, 38, 135, 0.15)",
        "glow-coral": "0 0 30px rgba(255, 107, 157, 0.3)",
        "glow-blue": "0 0 30px rgba(77, 150, 255, 0.3)",
        "glow-emerald": "0 0 30px rgba(16, 185, 129, 0.3)"
      },
      backdropBlur: {
        xs: "2px"
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease-in-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-glow": "pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 2s linear infinite",
        "spin-slow": "spin 3s linear infinite"
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" }
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" }
        },
        shimmer: {
          "0%": { backgroundPosition: "-1000px 0" },
          "100%": { backgroundPosition: "1000px 0" }
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" }
        }
      }
    }
  },
  plugins: []
} satisfies Config
