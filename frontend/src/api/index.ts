import type { ApiClient } from './types';
import { mockApi } from '../mocks/client';
import { realApi } from './real';

export { ApiError, getUserId, setUserId } from './real';
export type * from './types';
export const api: ApiClient = import.meta.env.VITE_USE_MOCK === 'true' ? mockApi : realApi;
