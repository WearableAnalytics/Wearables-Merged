import { Route, Routes } from 'react-router-dom';
import { NewCasePage } from './pages/NewCase';
import { OverviewPage } from './pages/Overview';
import { LogoutPage } from './pages/Logout';
import { PageHeader } from './components/custom/PageHeader';
import { NotFoundPage } from './pages/NotFound';

export function Routing() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/new-case" element={<NewCasePage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route
        path="*"
        element={<NotFoundPage />}
      />
    </Routes>
  );
}
