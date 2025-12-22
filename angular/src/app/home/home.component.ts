import { Component, AfterViewInit } from '@angular/core';
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
export class HomeComponent implements AfterViewInit {
  ngAfterViewInit() {
    // Fuerza la detección de cambios después de la navegación
    setTimeout(() => {
      // Esto dispara un nuevo ciclo de detección
      // No es elegante, pero funciona
    }, 50);
  }
}