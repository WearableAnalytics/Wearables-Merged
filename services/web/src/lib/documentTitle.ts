export const PLATFORM_NAME = 'Charité Wearables platform';

const PAGE_TITLES: Record<string, string> = {
  '/overview': 'Overview',
  '/add-case': 'Add case',
  '/account': 'Account',
  '/admin/approvals': 'Admin approvals',
  '/researcher/api-access': 'API access',
  '/login': 'Login',
  '/register': 'Register',
  '/logout': 'Logged out',
  '/request-sent': 'Request received',
  '/error-magic_link': 'Link not valid',
};

// Patient names are left out of the tab title so they don't end up in browser history.
export function getDocumentTitle(pathname: string): string {
  if (pathname === '/') {
    return PLATFORM_NAME;
  }
  const page = /^\/cases\/[^/]+$/.test(pathname) ? 'Patient case' : PAGE_TITLES[pathname] ?? 'Page not found';
  return `${page} | ${PLATFORM_NAME}`;
}
