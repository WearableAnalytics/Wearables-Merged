import { Route, Routes } from 'react-router-dom';
import { AddCasePage } from './pages/add-case/AddCase';
import { OverviewPage } from './pages/Overview';
import { LogoutPage } from './pages/Logout';
import { NotFoundPage } from './pages/NotFound';
import { CasePage } from './pages/case/CasePage';
import { PrivateRoute } from './components/PrivateRoute';
import { LandingPage } from './pages/Landing';
import { ErrorMagicLinkPage } from './pages/ErrorMagicLink';
import { AdminApprovalsPage } from './pages/AdminApprovals';
import { AccountPage } from './pages/Account';
import { AuthRequestSentPage } from './pages/AuthRequestSent';
import { AccessPage } from './pages/Access';
import { LoginPage } from './pages/Login';
import { RegisterPage } from './pages/Register';

export function Routing() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/overview"
        element={
          <PrivateRoute requirePractitionerOrAdmin>
            <OverviewPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/cases/:caseId"
        element={
          <PrivateRoute requirePractitionerOrAdmin>
            <CasePage />
          </PrivateRoute>
        }
      />
      <Route
        path="/add-case"
        element={
          <PrivateRoute requirePractitionerOrAdmin>
            <AddCasePage />
          </PrivateRoute>
        }
      />
      <Route
        path="/logout"
        element={<LogoutPage />}
      />
      <Route
        path="/account"
        element={
          <PrivateRoute>
            <AccountPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/admin/approvals"
        element={
          <PrivateRoute requireAdmin>
            <AdminApprovalsPage />
          </PrivateRoute>
        }
      />
      <Route path="/request-sent" element={<AuthRequestSentPage />} />
      <Route path="/access" element={<AccessPage />} />
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
