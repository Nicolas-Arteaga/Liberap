import type { CreateUpdateStrategyProfileDto, StrategyProfileDto } from './dtos/models';
import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class StrategyProfileService {
  private restService = inject(RestService);
  apiName = 'Default';
  

  create = (input: CreateUpdateStrategyProfileDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, StrategyProfileDto>({
      method: 'POST',
      url: '/api/app/strategy-profile',
      body: input,
    },
    { apiName: this.apiName,...config });
  

  delete = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, void>({
      method: 'DELETE',
      url: `/api/app/strategy-profile/${id}`,
    },
    { apiName: this.apiName,...config });
  

  get = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, StrategyProfileDto>({
      method: 'GET',
      url: `/api/app/strategy-profile/${id}`,
    },
    { apiName: this.apiName,...config });
  

  getList = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, StrategyProfileDto[]>({
      method: 'GET',
      url: '/api/app/strategy-profile',
    },
    { apiName: this.apiName,...config });
  

  toggleActive = (id: string, config?: Partial<Rest.Config>) =>
    this.restService.request<any, StrategyProfileDto>({
      method: 'POST',
      url: `/api/app/strategy-profile/${id}/toggle-active`,
    },
    { apiName: this.apiName,...config });
  

  update = (id: string, input: CreateUpdateStrategyProfileDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, StrategyProfileDto>({
      method: 'PUT',
      url: `/api/app/strategy-profile/${id}`,
      body: input,
    },
    { apiName: this.apiName,...config });
}