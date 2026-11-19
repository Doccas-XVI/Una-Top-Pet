// ============================================================================
// UnaTopPet - identidade visual compartilhada (Tailwind via CDN)
// Usado pelo app do tutor (mobile), pela interface web e pela área admin.
// Carregue DEPOIS de <script src="https://cdn.tailwindcss.com">.
//
// Paleta extraída do logo (logo.jpeg):
//   primary (grafite)  -> letras "UNA", contornos do cão e do gato
//   accent  (limão)    -> "Pet", patinha, língua e arcos do logo
//   bgLight (névoa)    -> fundo cinza-claro do banner
// ============================================================================
tailwind.config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Poppins", "Inter", "system-ui", "sans-serif"],
      },
      colors: {
        primary: {
          DEFAULT: "#2F3D41", light: "#45535A", dark: "#1F2A2E",
          50: "#F2F5F6", 100: "#E3E8EA", 200: "#C7D0D3", 300: "#A0ADB1", 400: "#76858A",
          500: "#57666B", 600: "#45535A", 700: "#39474E", 800: "#2F3D41", 900: "#1F2A2E",
        },
        accent: {
          DEFAULT: "#B5CC3A", light: "#CDE064", dark: "#82961F",
          50: "#F7FAE6", 100: "#EEF5C8", 200: "#DFEC98", 300: "#CDE064", 400: "#B5CC3A",
          500: "#A4BB2C", 600: "#82961F", 700: "#62711B", 800: "#4E5A1A", 900: "#414B19",
        },
        bgLight: "#EEF1F3",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(31,42,46,.04), 0 8px 24px -12px rgba(31,42,46,.16)",
        lift: "0 2px 4px rgba(31,42,46,.05), 0 18px 40px -18px rgba(31,42,46,.35)",
      },
    },
  },
};
