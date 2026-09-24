import {
  createContext,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

import type { ApplicationServices } from './services';

const ServicesContext = createContext<ApplicationServices | null>(null);

export function ServicesProvider({
  services,
  children,
}: {
  services: ApplicationServices;
  children: ReactNode;
}) {
  return (
    <ServicesContext.Provider value={services}>
      {children}
    </ServicesContext.Provider>
  );
}

export function useServices() {
  const services = useContext(ServicesContext);

  if (!services) throw new Error('Application services are not available.');

  return services;
}

export function useApi() {
  return useServices().api;
}

export function useSessionIdentity() {
  const services = useServices();

  return useSyncExternalStore(
    services.subscribeIdentity,
    services.getIdentity,
    () => '',
  );
}
