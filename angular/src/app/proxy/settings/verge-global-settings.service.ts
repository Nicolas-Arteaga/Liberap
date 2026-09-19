import { RestService, Rest } from '@abp/ng.core';
import { Injectable, inject } from '@angular/core';

export interface TrailStopGlobalSettingDto {
  enabled: boolean;
}

/**
 * ROUND 43 -- proxy manual (mismo estilo que el resto de servicios en
 * app/proxy/trading) para el switch maestro global de Trail-1, expuesto
 * por VergeGlobalSettingsAppService (Verge.Application/Settings).
 */
@Injectable({
  providedIn: 'root',
})
export class VergeGlobalSettingsService {
  private restService = inject(RestService);
  apiName = 'Default';

  getTrailStopSetting = (config?: Partial<Rest.Config>) =>
    this.restService.request<any, TrailStopGlobalSettingDto>(
      {
        method: 'GET',
        url: '/api/app/verge-global-settings/trail-stop-setting',
      },
      { apiName: this.apiName, ...config },
    );

  setTrailStopSetting = (input: TrailStopGlobalSettingDto, config?: Partial<Rest.Config>) =>
    this.restService.request<any, TrailStopGlobalSettingDto>(
      {
        method: 'POST',
        url: '/api/app/verge-global-settings/trail-stop-setting',
        body: input,
      },
      { apiName: this.apiName, ...config },
    );
}
