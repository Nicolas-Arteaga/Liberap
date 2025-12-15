  import { Component } from '@angular/core';
  import { CommonModule } from '@angular/common';
  import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
  import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
  import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';

  @Component({
    selector: 'app-home',
    standalone: true,
    imports: [
      CommonModule,
      CardContentComponent,
      CardIconComponent,
      GlassButtonComponent,
  ],
    templateUrl: './home.component.html'
  })
  export class HomeComponent {}
