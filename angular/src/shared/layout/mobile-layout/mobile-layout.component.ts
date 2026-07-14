import { Component, OnInit, OnDestroy, AfterViewInit, inject, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet, RouterLink, RouterLinkActive, NavigationEnd } from '@angular/router';
import {
  IonApp,
  IonContent,
  IonIcon
} from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import {
  homeOutline,
  pulseOutline,
  hardwareChipOutline,
  gridOutline,
  briefcaseOutline,
  listOutline,
  analyticsOutline,
  notificationsOutline,
  settingsOutline,
  personOutline,
  radioOutline,
  flashOutline,
  layersOutline,
  gitNetworkOutline
} from 'ionicons/icons';
import { Subscription, Observable } from 'rxjs';
import { map, filter } from 'rxjs/operators';

import { MobileTopBarComponent } from '../mobile-top-bar/mobile-top-bar.component';
import { MobileBottomNavComponent } from '../mobile-bottom-nav/mobile-bottom-nav.component';
import { AlertService } from '../../../app/services/alert.service';
import { VergeAlert } from '../../../app/shared/components/alerts/alerts.types';
import { AlertsComponent } from '../../../app/shared/components/alerts/alerts.component';
import { AiOrbComponent } from '../../components/ai-orb/ai-orb.component';

export interface TickerInfo {
  symbol: string;
  price: number;
  changePercent: number;
  change: number;
}

@Component({
  selector: 'app-mobile-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    IonApp,
    IonContent,
    IonIcon,
    MobileTopBarComponent,
    MobileBottomNavComponent,
    AlertsComponent,
    AiOrbComponent
  ],
  templateUrl: './mobile-layout.component.html',
  styleUrls: ['./mobile-layout.component.scss']
})
export class MobileLayoutComponent implements OnInit, OnDestroy {
  private alertService = inject(AlertService);
  private router = inject(Router);

  // Telemetría & Reloj
  currentTime = '00:00:00';
  uptime = '5d 14h 32m';
  latency = 18;
  currentRouteName = 'DASHBOARD CORE';

  private clockTimer: any;
  private latencyTimer: any;
  private uptimeTimer: any;
  private baseUptimeMinutes = 8072;
  private routerSub?: Subscription;

  // Tickers Binance WebSocket
  tickers: TickerInfo[] = [
    { symbol: 'BTCUSDT', price: 76998.30, changePercent: 0.82, change: 1 },
    { symbol: 'ETHUSDT', price: 3842.15, changePercent: 1.25, change: 1 },
    { symbol: 'SOLUSDT', price: 178.45, changePercent: 2.15, change: 1 },
    { symbol: 'BNBUSDT', price: 596.32, changePercent: -0.65, change: -1 },
    { symbol: 'XRPUSDT', price: 0.6123, changePercent: 1.12, change: 1 }
  ];
  private ws: WebSocket | null = null;

  showNotifications = false;
  notifications$: Observable<VergeAlert[]> = this.alertService.alerts$.pipe(
    map(alerts => alerts.filter(a => (a.confidence || 0) >= 70))
  );

  constructor() {
    addIcons({
      homeOutline, pulseOutline, hardwareChipOutline, gridOutline,
      briefcaseOutline, listOutline, analyticsOutline,
      notificationsOutline, settingsOutline, personOutline,
      radioOutline, flashOutline, layersOutline, gitNetworkOutline
    });
  }

  ngOnInit() {
    this.updateRouteName();
    this.startTrackers();
    this.initWebsocket();
    this.routerSub = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(() => { this.updateRouteName(); });
  }

  ngOnDestroy() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    if (this.latencyTimer) clearInterval(this.latencyTimer);
    if (this.uptimeTimer) clearInterval(this.uptimeTimer);
    if (this.ws) { try { this.ws.close(); } catch (e) {} }
    this.routerSub?.unsubscribe();
  }

  get unreadCount(): number {
    return this.alertService.getUnreadCount();
  }

  toggleNotificationPanel() {
    this.showNotifications = !this.showNotifications;
  }

  markAllAsRead() {
    this.alertService.markAllAsRead();
  }

  markAsRead(id: string) {
    this.alertService.markAsRead(id);
  }

  onNotificationClick(id: string) {
    this.showNotifications = false;
    this.alertService.handleAlertClick(id);
  }

  private updateRouteName() {
    const url = this.router.url.split('?')[0];
    if (url === '/' || url === '/home')           this.currentRouteName = 'DASHBOARD CORE';
    else if (url === '/nexus-15')                 this.currentRouteName = 'NEXUS-15 PREDICTIVE CORE';
    else if (url === '/nexus-5')                  this.currentRouteName = 'NEXUS-5 IGNITION CORE';
    else if (url === '/agent')                    this.currentRouteName = 'AI TRADING AGENT';
    else if (url === '/agent-audit')              this.currentRouteName = 'AUDITORÍA DE OPERACIONES';
    else if (url.startsWith('/strategies'))       this.currentRouteName = 'ESTRATEGIAS DE INVERSIÓN';
    else if (url === '/dashboard-advanced')       this.currentRouteName = 'POSICIONES ABIERTAS';
    else if (url === '/history')                  this.currentRouteName = 'HISTORIAL DE OPERACIONES';
    else if (url === '/backtesting')              this.currentRouteName = 'BACKTESTING SIMULADO';
    else if (url === '/alerts')                   this.currentRouteName = 'ALERTAS DEL MERCADO';
    else if (url === '/profile')                  this.currentRouteName = 'CONFIGURACIÓN DEL SISTEMA';
    else if (url.startsWith('/admin'))            this.currentRouteName = 'PANEL DE ADMINISTRACIÓN';
    else                                          this.currentRouteName = 'VERGE INTELLIGENCE';
  }

  private startTrackers() {
    const updateClock = () => {
      const now = new Date();
      this.currentTime = now.toLocaleTimeString('es-AR', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false, timeZone: 'America/Argentina/Buenos_Aires'
      });
    };
    updateClock();
    this.clockTimer = setInterval(updateClock, 1000);

    this.latencyTimer = setInterval(() => {
      this.latency = Math.floor(Math.random() * 9) + 14;
    }, 3000);

    const updateUptime = () => {
      this.baseUptimeMinutes++;
      const days    = Math.floor(this.baseUptimeMinutes / 1440);
      const hours   = Math.floor((this.baseUptimeMinutes % 1440) / 60);
      const minutes = this.baseUptimeMinutes % 60;
      this.uptime = `${days}d ${hours}h ${minutes}m`;
    };
    updateUptime();
    this.uptimeTimer = setInterval(updateUptime, 60000);
  }

  private initWebsocket() {
    try {
      const streams = 'btcusdt@ticker/ethusdt@ticker/solusdt@ticker/bnbusdt@ticker/xrpusdt@ticker';
      this.ws = new WebSocket(`wss://fstream.binance.com/stream?streams=${streams}`);

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg?.data) {
          const idx = this.tickers.findIndex(t => t.symbol === msg.data.s);
          if (idx !== -1) {
            const pct = parseFloat(msg.data.P);
            this.tickers[idx].price = parseFloat(msg.data.c);
            this.tickers[idx].changePercent = pct;
            this.tickers[idx].change = pct >= 0 ? 1 : -1;
          }
        }
      };

      this.ws.onerror = (err) => { console.warn('[Layout WS] Error:', err); };

      this.ws.onclose = () => {
        setTimeout(() => {
          if (!this.ws || this.ws.readyState === WebSocket.CLOSED) this.initWebsocket();
        }, 5000);
      };
    } catch (e) {
      console.error('[Layout WS] Init exception:', e);
    }
  }
}