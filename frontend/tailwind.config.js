export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { ink: "#1D2B3A", paper: "#F3F5F7", teal: { DEFAULT: "#0E8F7E", dark: "#0A6B5E" }, amber: { DEFAULT: "#E7A33E" }, plum: "#7B4B94" },
    fontFamily: { sans: ['"IBM Plex Sans"', "system-ui", "Segoe UI", "sans-serif"] } } },
  plugins: [],
};
