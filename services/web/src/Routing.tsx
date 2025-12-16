import { Route, Routes } from 'react-router-dom';
import { AddCasePage } from './pages/add-case/AddCase';
import { OverviewPage } from './pages/Overview';
import { LogoutPage } from './pages/Logout';
import { NotFoundPage } from './pages/NotFound';
import { CasePage } from './pages/case/CasePage';
import { LoginPage} from './pages/Login';
import { RegisterPage } from './pages/Register';

export function Routing() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/cases/:caseId" element={<CasePage />} />
      <Route path="/add-case" element={<AddCasePage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="*"
        element={<NotFoundPage />}
      />
    </Routes>
  );
}
