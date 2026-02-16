import { ApplicationConfig, importProvidersFrom } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideAnimations } from '@angular/platform-browser/animations';
import { APP_ROUTES } from './app.routes';
import { APP_ROUTE_PROVIDER } from './route.provider';
import { provideAbpCore, withOptions } from '@abp/ng.core';
import { provideAbpOAuth } from '@abp/ng.oauth';
import { provideSettingManagementConfig } from '@abp/ng.setting-management/config';
import { provideAccountConfig } from '@abp/ng.account/config';
import { provideIdentityConfig } from '@abp/ng.identity/config';
import { provideTenantManagementConfig } from '@abp/ng.tenant-management/config';
import { provideFeatureManagementConfig } from '@abp/ng.feature-management';
import {
  ThemeBasicModule,
  provideThemeBasicConfig,
} from '@abp/ng.theme.basic';
import {
  ThemeSharedModule,
  provideAbpThemeShared,
} from '@abp/ng.theme.shared';

import { environment } from '../environments/environment';
import { registerLocaleForEsBuild } from '@abp/ng.core/locale';

import { provideIonicAngular } from '@ionic/angular/standalone';
import { provideHttpClient, withInterceptorsFromDi, HTTP_INTERCEPTORS } from '@angular/common/http';
import { JwtInterceptor } from './interceptors/jwt.interceptor';

/* ======================================================
   IONICONS – REGISTRO MANUAL (OBLIGATORIO EN STANDALONE)
   ====================================================== */
import { addIcons } from 'ionicons';
import {
  calendarOutline,
  homeOutline,
  cardOutline,
  personOutline,
  addCircleOutline,
  chatbubbleOutline,
  timeOutline,
  cashOutline,
  businessOutline,
  notificationsOutline,
  lockClosedOutline,
  settingsOutline,
  chevronBackOutline,
  trashOutline,
  createOutline,
  checkmarkCircleOutline,
  arrowBackOutline,
  checkmark,
  close,
  logoUsd,
  peopleOutline,
  analyticsOutline,
  mailOutline,
  documentOutline,
  readerOutline,
  receiptOutline,
  calculatorOutline,
  statsChartOutline,
  pricetagOutline,
  // Iconos faltantes detectados:
  flashOutline,
  trendingUpOutline,
  trendingDownOutline,
  warningOutline,
  searchOutline,
  rocketOutline,
  shieldOutline,
  logOutOutline,
  informationCircleOutline,
  playOutline,
  arrowUpOutline,
  arrowDownOutline,
  addOutline,
  notificationsOffOutline,
  closeCircleOutline,
  saveOutline,
  pauseOutline,
  sparklesOutline,
  keyOutline,
  linkOutline,
  cloudDownloadOutline,
  helpCircleOutline
} from 'ionicons/icons';

addIcons({
  'calendar-outline': calendarOutline,
  'home-outline': homeOutline,
  'card-outline': cardOutline,
  'person-outline': personOutline,
  'add-circle-outline': addCircleOutline,
  'chatbubble-outline': chatbubbleOutline,
  'time-outline': timeOutline,
  'cash-outline': cashOutline,
  'business-outline': businessOutline,
  'notifications-outline': notificationsOutline,
  'lock-closed-outline': lockClosedOutline,
  'settings-outline': settingsOutline,
  'chevron-back-outline': chevronBackOutline,
  'trash-outline': trashOutline,
  'create-outline': createOutline,
  'checkmark-circle-outline': checkmarkCircleOutline,
  'arrow-back-outline': arrowBackOutline,
  'checkmark': checkmark,
  'close': close,
  'logo-usd': logoUsd,
  'people-outline': peopleOutline,
  'analytics-outline': analyticsOutline,
  'mail-outline': mailOutline,
  'document-outline': documentOutline,
  'reader-outline': readerOutline,
  'receipt-outline': receiptOutline,
  'calculator-outline': calculatorOutline,
  'stats-chart-outline': statsChartOutline,
  'pricetag-outline': pricetagOutline,
  'flash-outline': flashOutline,
  'trending-up-outline': trendingUpOutline,
  'trending-down-outline': trendingDownOutline,
  'warning-outline': warningOutline,
  'search-outline': searchOutline,
  'rocket-outline': rocketOutline,
  'shield-outline': shieldOutline,
  'log-out-outline': logOutOutline,
  'information-circle-outline': informationCircleOutline,
  'play-outline': playOutline,
  'arrow-up-outline': arrowUpOutline,
  'arrow-down-outline': arrowDownOutline,
  'add-outline': addOutline,
  'notifications-off-outline': notificationsOffOutline,
  'close-circle-outline': closeCircleOutline,
  'save-outline': saveOutline,
  'pause-outline': pauseOutline,
  'sparkles-outline': sparklesOutline,
  'key-outline': keyOutline,
  'link-outline': linkOutline,
  'cloud-download-outline': cloudDownloadOutline,
  'help-circle-outline': helpCircleOutline
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(APP_ROUTES),
    APP_ROUTE_PROVIDER,

    provideAnimations(),

    provideAbpCore(
      withOptions({
        environment,
        registerLocaleFn: registerLocaleForEsBuild(),
      })
    ),

    provideAbpOAuth(), // Re-habilitado para silenciar advertencia de ABP
    provideSettingManagementConfig(),
    provideAccountConfig(),
    provideIdentityConfig(),
    provideTenantManagementConfig(),
    provideFeatureManagementConfig(),

    importProvidersFrom(ThemeBasicModule, ThemeSharedModule),
    provideThemeBasicConfig(),
    provideAbpThemeShared(),

    provideHttpClient(withInterceptorsFromDi()),
    {
      provide: HTTP_INTERCEPTORS,
      useClass: JwtInterceptor,
      multi: true
    },

    /* IONIC STANDALONE */
    provideIonicAngular({
      mode: 'md',
    }),
  ],
};
