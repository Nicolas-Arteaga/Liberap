import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class AgentService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  startAgent = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/start-agent',
    },
    { apiName: this.apiName,...config });
  

  startServer = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/start-server',
    },
    { apiName: this.apiName,...config });
  

  stopAgent = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/stop-agent',
    },
    { apiName: this.apiName,...config });
  

  stopServer = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/agent/stop-server',
    },
    { apiName: this.apiName,...config });
}