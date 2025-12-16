import { useLocation, useNavigate } from 'react-router-dom';
import { GuestNavbar } from './components/custom/navbar/guestNavbar';
import { Routing } from './Routing';

const GUEST_ROUTES = ['/', '/register', '/login'];

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="bg-sky-50 text-slate-900 min-h-screen">
      <GuestNavbar alwaysGuestRoutes={GUEST_ROUTES} navigate={navigate} location={location} />

      <main className="pt-24 pb-[72px] px-[clamp(16px,4vw,48px)]">
        <div className="max-w-[1100px] mx-auto">
          <Routing />
        </div>
      </main>
    </div>
  );
}

export default App;
