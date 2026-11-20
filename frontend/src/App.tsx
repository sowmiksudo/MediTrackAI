import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Layout } from "./components/Layout";
import CheckIn from "./pages/CheckIn";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import PublicBrief from "./pages/PublicBrief";
import Summaries from "./pages/Summaries";
import Upload from "./pages/Upload";
import VisitPrep from "./pages/VisitPrep";

const Docs = lazy(() => import("./pages/Docs"));

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="flex h-screen items-center justify-center text-muted-foreground">Loading MediTrackAI...</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/brief/:token" element={<PublicBrief />} />
            <Route
              path="/docs"
              element={
                <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading Live Docs...</div>}>
                  <Docs />
                </Suspense>
              }
            />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<CheckIn />} />
              <Route path="upload" element={<Upload />} />
              <Route path="summaries" element={<Summaries />} />
              <Route path="visit-prep" element={<VisitPrep />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
