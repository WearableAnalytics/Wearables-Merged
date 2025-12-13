import { Route, Routes } from 'react-router-dom';
import { AddCasePage } from './pages/AddCase/AddCase';
import { OverviewPage } from './pages/Overview';
import { LogoutPage } from './pages/Logout';
import { PageHeader } from './components/custom/PageHeader';
import { NotFoundPage } from './pages/NotFound';

export function Routing() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/add-case" element={<AddCasePage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route
        path="*"
        element={<NotFoundPage />}
      />
    </Routes>
  );
}
