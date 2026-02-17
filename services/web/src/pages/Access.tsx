import { Navigate } from 'react-router-dom';

export function AccessPage() {
  return <Navigate to="/login" replace />;
}
