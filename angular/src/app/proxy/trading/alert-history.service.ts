import type { AlertHistoryDto } from './dtos/models';
import type { GetAlertHistoryInput } from './models';
import { RestService, Rest } from '@abp/ng.core';
import type { PagedResultDto } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class AlertHistoryService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  getHighConfidenceNotifications = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, AlertHistoryDto[]>({
      method: 'GET',
      url: '/api/app/alert-history/high-confidence-notifications',
    },
    { apiName: this.apiName,...config });
  

  getList = (input: GetAlertHistoryInput, config?: Partial<Rest.Config>) =>
    this.restService.request<any, PagedResultDto<AlertHistoryDto>>({
      method: 'GET',
      url: '/api/app/alert-history',
      params: { symbol: input.symbol, style: input.style, status: input.status, isRead: input.isRead, sorting: input.sorting, skipCount: input.skipCount, maxResultCount: input.maxResultCount },
    },
    { apiName: this.apiName,...config });
  

  markAllAsRead = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: '/api/app/alert-history/mark-all-as-read',
    },
    { apiName: this.apiName,...config });
  

  markAsRead = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'POST',
      url: `/api/app/alert-history/${id}/mark-as-read`,
    },
    { apiName: this.apiName,...config });
}