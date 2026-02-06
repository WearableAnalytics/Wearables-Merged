import { useLocation, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Navbar } from './components/custom/navbar/Navbar';
import { Routing } from './Routing';

const GUEST_ROUTES = ['/', '/access', '/register', '/login', '/request-sent', '/error-magic_link'];

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="bg-sky-50 text-slate-900 min-h-screen">
      <Navbar alwaysGuestRoutes={GUEST_ROUTES} navigate={navigate} location={location} />
      <Toaster position="top-right" richColors closeButton />

      <main className="pt-24 pb-[72px] px-[clamp(16px,4vw,48px)]">
        <div className="max-w-[1100px] mx-auto">
          <Routing />
        </div>
      </main>
    </div>
  );
}

export default App;
