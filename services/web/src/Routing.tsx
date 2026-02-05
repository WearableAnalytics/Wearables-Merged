import { Route, Routes } from 'react-router-dom';
import { AddCasePage } from './pages/add-case/AddCase';
import { OverviewPage } from './pages/Overview';
import { LogoutPage } from './pages/Logout';
import { NotFoundPage } from './pages/NotFound';
import { CasePage } from './pages/case/CasePage';
import { LoginPage } from './pages/Login';
import { RegisterPage } from './pages/Register';
import { PrivateRoute } from './components/PrivateRoute';
import { LandingPage } from './pages/Landing';
import { ErrorMagicLinkPage } from './pages/ErrorMagicLink';
import { PatientMonitoringPage } from './pages/PatientMonitoring';

export function Routing() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/overview"
        element={
          <PrivateRoute>
            <OverviewPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/cases/:caseId"
        element={
          <PrivateRoute>
            <CasePage />
          </PrivateRoute>
        }
      />
      <Route
        path="/add-case"
        element={
          <PrivateRoute>
            <AddCasePage />
          </PrivateRoute>
        }
      />
      <Route
        path="/logout"
        element={
          <PrivateRoute>
            <LogoutPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/monitoring/:caseId"
        element={
          <PrivateRoute>
            <PatientMonitoringPage />
          </PrivateRoute>
        }
      />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/error-magic_link" element={<ErrorMagicLinkPage />} />
      <Route
        path="*"
        element={<NotFoundPage />}
      />
    </Routes>
  );
}
