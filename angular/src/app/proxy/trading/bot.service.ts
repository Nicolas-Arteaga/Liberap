import type { BotPairDto } from './models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class BotService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getActivePairs = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, BotPairDto[]>({
      method: 'GET',
      url: '/api/app/bot/active-pairs',
    },
    { apiName: this.apiName,...config });
}