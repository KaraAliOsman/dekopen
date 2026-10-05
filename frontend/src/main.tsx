import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-400-italic.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { AuthSessionProvider } from "./auth/AuthSessionProvider";
import "./index.css";
import "./styles/tokens.css";
import { ThemeProvider } from "./theme/ThemeProvider";
import { ConfirmProvider, ToastProvider } from "./ui";
import "./ui/ui.css";
import { installSpanishValidation } from "./validation";

// Validación en español para todo el documento — cada <form noValidate>
// queda cubierto sin cableado por página (§4 voz y microcopy).
installSpanishValidation();

const container = document.getElementById("root");
if (container === null) throw new Error("Frontend root element is missing");

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Route re-mounts shouldn't instantly re-hit the API — most reads
      // stay accurate within 30 s and mutations invalidate explicitly.
      staleTime: 30_000,
    },
  },
});

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthSessionProvider>
          <ConfirmProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </ConfirmProvider>
        </AuthSessionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
