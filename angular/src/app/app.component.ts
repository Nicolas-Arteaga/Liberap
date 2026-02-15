import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { LoaderBarComponent } from '@abp/ng.theme.shared';

@Component({
  selector: 'app-root',
  template: `
    <abp-loader-bar />
    <router-outlet />
  `,
  standalone: true,
  imports: [LoaderBarComponent, RouterOutlet],
})
export class AppComponent {
  constructor() {
    this.monitorStorage();
  }

  private monitorStorage() {
    console.log('🌐 App Origin:', window.location.origin);

    const originalSetItem = localStorage.setItem;
    localStorage.setItem = function (key: string, value: string) {
      if (key === 'verge_access_token' || key === 'access_token') {
        console.log(`💾 SE ESTÁ GUARDANDO EL TOKEN: "${key}" = "${value ? 'VALOR PRESENTE' : 'VACÍO'}"`, new Error().stack);
      }
      return originalSetItem.apply(this, [key, value]);
    };

    const originalRemoveItem = localStorage.removeItem;
    localStorage.removeItem = function (key: string) {
      if (key === 'verge_access_token' || key === 'access_token') {
        console.error('🔥 ALGUIEN ESTÁ BORRANDO EL TOKEN!', new Error().stack);
      }
      return originalRemoveItem.apply(this, [key]);
    };

    const originalClear = localStorage.clear;
    localStorage.clear = function () {
      console.warn('🧹 localStorage.clear() detectado!', new Error().stack);
      return originalClear.apply(this);
    };
  }
}
