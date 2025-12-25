import { Component, AfterViewInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { CardIconComponent } from 'src/shared/components/card-icon/card-icon.component';
import { GlassButtonComponent } from 'src/shared/components/glass-button/glass-button.component';
import { CardContentComponent } from 'src/shared/components/card-content/card-content.component';
import { IonIcon } from "@ionic/angular/standalone";
import { IconService } from 'src/shared/services/icon.service';  

@Component({
  selector: 'app-profile',
  standalone: true,
  imports: [
    CommonModule,
    CardIconComponent,
    GlassButtonComponent,
    CardContentComponent,
    IonIcon
  ],
  templateUrl: './profile.component.html',
  styleUrls: ['./profile.component.scss']
})
export class ProfileComponent implements AfterViewInit {
  
  private router = inject(Router);
  private iconService = inject(IconService);  

  ngAfterViewInit() {
    this.iconService.fixMissingIcons();  
  }

  onEditProfile() {
    console.log('Editar perfil');
  }

  onPersonalInfo() {
    console.log('Información personal');
  }

  onPaymentMethods() {
    console.log('Métodos de pago');
  }

  onNotifications() {
    console.log('Notificaciones');
  }

  onSecurity() {
    console.log('Seguridad y privacidad');
  }

  onPreferences() {
    console.log('Preferencias de la app');
  }

 onLogout() {
    if (confirm('¿Estás seguro que deseas cerrar sesión?')) {
      console.log('Sesión cerrada');
      window.location.href = '/login';
    }
  }
}