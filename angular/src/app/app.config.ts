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
  settingsOutline       
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
  'settings-outline': settingsOutline              
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

    provideAbpOAuth(),
    provideSettingManagementConfig(),
    provideAccountConfig(),
    provideIdentityConfig(),
    provideTenantManagementConfig(),
    provideFeatureManagementConfig(),

    importProvidersFrom(ThemeBasicModule, ThemeSharedModule),
    provideThemeBasicConfig(),
    provideAbpThemeShared(),

    /* IONIC STANDALONE */
    provideIonicAngular({
      mode: 'md',
    }),
  ],
};
