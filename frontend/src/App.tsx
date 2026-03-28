import React, { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import NotFound from "./pages/NotFound.tsx";

const queryClient = new QueryClient();

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error?: Error }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    console.error("Error caught by boundary:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: '#fee', padding: '24px' }}>
          <div style={{ maxWidth: '400px' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 'bold', color: '#7c2d12', marginBottom: '16px' }}>Application Error</h1>
            <p style={{ color: '#9a3412', marginBottom: '16px' }}>{this.state.error?.message}</p>
            <pre style={{ fontSize: '12px', backgroundColor: '#fecaca', padding: '16px', borderRadius: '4px', maxHeight: '256px', overflow: 'auto', color: '#7c2d12' }}>
              {this.state.error?.stack}
            </pre>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const App = () => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    console.log("App mounted");
    setMounted(true);
    
    // Ensure root div has proper height
    const root = document.getElementById('root');
    if (root) {
      root.style.height = '100vh';
      root.style.width = '100vw';
      root.style.overflow = 'hidden';
    }
  }, []);

  if (!mounted) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: '#f5f5f0' }}>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Index />} />
              {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};

export default App;
