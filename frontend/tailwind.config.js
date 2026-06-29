/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17202a",
        panel: "#f7f8fa",
        line: "#d8dee7",
        accent: "#0f8b8d",
        danger: "#b42318",
        warn: "#b7791f"
      }
    }
  },
  plugins: []
};
