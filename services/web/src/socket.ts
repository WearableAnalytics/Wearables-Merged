import { io } from 'socket.io-client';
import { appRuntimeConfig } from './config/runtimeConfig';

export const socket = io(appRuntimeConfig.socketUrl || undefined, {
  withCredentials: true,
});
