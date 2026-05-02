import { Environment } from '@abp/ng.core';

const baseUrl = 'http://localhost:4200';

const oAuthConfig = {
  issuer: 'https://localhost:44396/',
  redirectUri: baseUrl,
  clientId: 'Verge_App',
  responseType: 'code',
  scope: 'offline_access Verge',
  requireHttps: true,
};

export const environment = {
  production: false,
  /** Motor LSE (FastAPI en docker: map host 8005 → container 8000) */
  pythonAiUrl: 'http://localhost:8005',
  application: {
    baseUrl,
    name: 'Verge',
  },
  oAuthConfig,
  apis: {
    default: {
      url: 'https://localhost:44396',
      rootNamespace: 'Verge',
    },
    AbpAccountPublic: {
      url: oAuthConfig.issuer,
      rootNamespace: 'AbpAccountPublic',
    },
  },
} as Environment;
