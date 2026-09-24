import type { SessionInfo } from '@/common/api/generated/data-contracts';
import type { ApplicationServices } from '@/common/api/services';

export type RouterContext = { services: ApplicationServices };

export type AuthenticatedContext = RouterContext & {
  session: SessionInfo;
  capabilityAllowed?: boolean;
};
