import { Component, inject } from '@angular/core';
import { DynamicLayoutComponent, ReplaceableComponentsService } from '@abp/ng.core';
import { LoaderBarComponent } from '@abp/ng.theme.shared';
import { eThemeBasicComponents } from '@abp/ng.theme.basic';
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

  constructor() {
    this.replaceableComponents.add({
      component: MobileLayoutComponent,
      key: eThemeBasicComponents.ApplicationLayout,
    });
  }
}