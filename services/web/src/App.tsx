import { useLocation, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Navbar } from './components/custom/navbar/Navbar';
import { Routing } from './Routing';
import { useTheme } from './context/ThemeContext';

const GUEST_ROUTES = ['/', '/access', '/register', '/login', '/request-sent', '/error-magic_link'];

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark } = useTheme();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar alwaysGuestRoutes={GUEST_ROUTES} navigate={navigate} location={location} />
      <Toaster position="top-right" richColors closeButton theme={isDark ? 'dark' : 'light'} />

      <main className="pt-24 pb-[72px] px-[clamp(16px,4vw,48px)]">
        <div className="max-w-[1100px] mx-auto">
          <Routing />
        </div>
      </main>
    </div>
  );
}

export default App;
