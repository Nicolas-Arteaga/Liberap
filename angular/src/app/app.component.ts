import { Component, inject } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { DynamicLayoutComponent, ReplaceableComponentsService } from '@abp/ng.core';
import { LoaderBarComponent } from '@abp/ng.theme.shared';
import { EmptyLayoutComponent, eThemeBasicComponents } from '@abp/ng.theme.basic';
import { MobileLayoutComponent } from 'src/shared/layout/mobile-layout/mobile-layout.component';

@Component({
  selector: 'app-root',
  template: `
    <abp-loader-bar />
    <abp-dynamic-layout />
  `,
  imports: [LoaderBarComponent, DynamicLayoutComponent],
})
export class AppComponent {
  private replaceableComponents = inject(ReplaceableComponentsService);
  private router = inject(Router);

  constructor() {
    // Escuchar cambios de ruta para cambiar el layout
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      this.updateLayout(event.urlAfterRedirects);
    });

    // Configuración inicial
    this.updateLayout(this.router.url);
  }

  private updateLayout(url: string): void {
    const isLoginPage = url === '/login' || url.startsWith('/login');
    
    if (isLoginPage) {
      // Usar layout vacío para login
      this.replaceableComponents.add({
        component: EmptyLayoutComponent,
        key: eThemeBasicComponents.ApplicationLayout,
      });
    } else {
      // Usar layout móvil para el resto
      this.replaceableComponents.add({
        component: MobileLayoutComponent,
        key: eThemeBasicComponents.ApplicationLayout,
      });
    }
  }
}