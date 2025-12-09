import { Environment } from '@abp/ng.core';

const baseUrl = 'http://localhost:4200';

const oAuthConfig = {
  issuer: 'https://localhost:44396/',
  redirectUri: baseUrl,
  clientId: 'Liberap_App',
  responseType: 'code',
  scope: 'offline_access Liberap',
  requireHttps: true,
};

export const environment = {
  production: false,
  application: {
    baseUrl,
    name: 'Liberap',
  },
  oAuthConfig,
  apis: {
    default: {
      url: 'https://localhost:44396',
      rootNamespace: 'Liberap',
    },
    AbpAccountPublic: {
      url: oAuthConfig.issuer,
      rootNamespace: 'AbpAccountPublic',
    },
  },
} as Environment;
