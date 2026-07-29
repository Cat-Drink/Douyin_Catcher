import { Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "./layouts/AppShell";
import DownloadPage from "./pages/DownloadPage";
import BatchFetchPage from "./pages/BatchFetchPage";
import ProfileFetchPage from "./pages/ProfileFetchPage";
import CookiePage from "./pages/CookiePage";
import SettingsPage from "./pages/SettingsPage";
import OnboardingPage from "./pages/OnboardingPage";

function App() {
  return (
    <Routes>
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/download" replace />} />
        <Route path="/download" element={<DownloadPage />} />
        <Route path="/batch-fetch" element={<BatchFetchPage />} />
        <Route path="/profile-fetch" element={<ProfileFetchPage />} />
        <Route path="/cookie" element={<CookiePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default App;