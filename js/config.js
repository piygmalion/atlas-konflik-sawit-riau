/**
 * Konfigurasi sumber data Atlas.
 * Mode auto: coba Supabase dulu, fallback ke data/ lokal.
 */
window.ATLAS_CONFIG = {
  dataSource: "auto",
  supabaseUrl: "https://vwjvahgkmypfklwpyipf.supabase.co",
  supabaseAnonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ3anZhaGdrbXlwZmtsd3B5aXBmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0MjU3OTAsImV4cCI6MjEwMTAwMTc5MH0._VKUX0Mxtt2LOX1dArL954BfwABFQWYuRgyJHhXoBdg",
  apiBaseUrl: "",
  remoteTimeoutMs: 8000,
};
