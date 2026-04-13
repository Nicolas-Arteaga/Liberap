import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { addIcons } from 'ionicons';
import { personOutline, notificationsOutline, checkmarkDoneOutline, notificationsOffOutline, pulseOutline, trendingUpOutline, layersOutline, rocketOutline, analyticsOutline, cashOutline, warningOutline, hardwareChipOutline } from 'ionicons/icons';
import { RouterLink } from '@angular/router';
import {
  IonHeader,
  IonToolbar,
  IonButton,
  IonIcon
} from '@ionic/angular/standalone';
import { AlertsComponent } from '../../../app/shared/components/alerts/alerts.component';
import { AlertService } from '../../../app/services/alert.service';
import { VergeAlert } from '../../../app/shared/components/alerts/alerts.types';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

@Component({
  selector: 'app-mobile-top-bar',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    IonHeader,
    IonToolbar,
    IonButton,
    IonIcon,
    AlertsComponent
  ],
  templateUrl: './mobile-top-bar.component.html',
  styleUrls: ['./mobile-top-bar.component.scss']
})
export class MobileTopBarComponent {
  private alertService = inject(AlertService);

  // Fase 6: Solo mostrar alertas >= 70% en el dropdown
  notifications$: Observable<VergeAlert[]> = this.alertService.alerts$.pipe(
    map(alerts => alerts.filter(a => (a.confidence || 0) >= 70))
  );
  showNotifications = false;

  constructor() {
    addIcons({ personOutline, notificationsOutline, checkmarkDoneOutline, notificationsOffOutline, pulseOutline, trendingUpOutline, layersOutline, rocketOutline, analyticsOutline, cashOutline, warningOutline, hardwareChipOutline });
  }

  get unreadCount(): number {
    return this.alertService.getUnreadCount();
  }

  toggleNotificationPanel() {
    console.log('[MobileTopBar] Campana clickeada. Estado anterior:', this.showNotifications);
    this.showNotifications = !this.showNotifications;
    console.log('[MobileTopBar] Nuevo estado showNotifications:', this.showNotifications);
  }

  markAllAsRead() {
    this.alertService.markAllAsRead();
  }

  markAsRead(id: string) {
    this.alertService.markAsRead(id);
  }

  onNotificationClick(id: string) {
    console.log('[MobileTopBar] Notificación clickeada:', id);
    this.showNotifications = false;
    this.alertService.handleAlertClick(id);
  }

  onProfileClick() { }
}
