import type { Config } from "tailwindcss";

// Mobile-first defaults. Phone is the primary target; desktop is the override.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        felt: {
          DEFAULT: "#0d5132",
          dark: "#073a23",
        },
        chip: {
          red: "#c03030",
          black: "#1a1a1a",
          green: "#1f6f43",
          blue: "#1f4f8f",
        },
      },
      // Phone-friendly minimums: 44px touch targets, safe-area aware.
      spacing: {
        "safe-top": "env(safe-area-inset-top)",
        "safe-bot": "env(safe-area-inset-bottom)",
      },
      minHeight: {
        touch: "44px",
        screen: "100dvh",
      },
      minWidth: {
        touch: "44px",
      },
      height: {
        screen: "100dvh",
      },
    },
  },
  plugins: [],
} satisfies Config;
