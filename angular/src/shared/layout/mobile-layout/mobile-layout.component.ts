import { Component, OnInit, OnDestroy, AfterViewInit, ViewChild, ElementRef, inject, NgZone } from '@angular/core';
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
  personOutline
} from 'ionicons/icons';
import { Subscription, Observable } from 'rxjs';
import { map, filter } from 'rxjs/operators';

import { MobileTopBarComponent } from '../mobile-top-bar/mobile-top-bar.component';
import { MobileBottomNavComponent } from '../mobile-bottom-nav/mobile-bottom-nav.component';
import { AlertService } from '../../../app/services/alert.service';
import { VergeAlert } from '../../../app/shared/components/alerts/alerts.types';
import { AlertsComponent } from '../../../app/shared/components/alerts/alerts.component';

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
    AlertsComponent
  ],
  templateUrl: './mobile-layout.component.html',
  styleUrls: ['./mobile-layout.component.scss']
})
export class MobileLayoutComponent implements OnInit, AfterViewInit, OnDestroy {
  private alertService = inject(AlertService);
  private router = inject(Router);
  private ngZone = inject(NgZone);

  @ViewChild('krakenCanvas', { static: false }) krakenCanvas?: ElementRef<HTMLCanvasElement>;
  private animationFrameId: number | null = null;
  private resizeListener?: () => void;

  // Telemetría & Reloj
  currentTime = '00:00:00';
  uptime = '5d 14h 32m';
  latency = 18;
  currentRouteName = 'DASHBOARD CORE';

  private clockTimer: any;
  private latencyTimer: any;
  private uptimeTimer: any;
  private baseUptimeMinutes = 8072; // ~5d 14h 32m
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

  // Notificaciones dropdown
  showNotifications = false;
  notifications$: Observable<VergeAlert[]> = this.alertService.alerts$.pipe(
    map(alerts => alerts.filter(a => (a.confidence || 0) >= 70))
  );

  constructor() {
    addIcons({
      homeOutline,
      pulseOutline,
      hardwareChipOutline,
      gridOutline,
      briefcaseOutline,
      listOutline,
      analyticsOutline,
      notificationsOutline,
      settingsOutline,
      personOutline
    });
  }

  ngOnInit() {
    this.updateRouteName();
    this.startTrackers();
    this.initWebsocket();

    // Suscribirse a los cambios de ruta para breadcrumbs/header superior
    this.routerSub = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(() => {
      this.updateRouteName();
    });
  }

  ngAfterViewInit() {
    // Run after a short delay to ensure DOM layout is completely settled
    setTimeout(() => {
      this.ngZone.runOutsideAngular(() => {
        this.initKrakenAnimation();
      });
    }, 100);
  }

  ngOnDestroy() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    if (this.latencyTimer) clearInterval(this.latencyTimer);
    if (this.uptimeTimer) clearInterval(this.uptimeTimer);
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {}
    }
    this.routerSub?.unsubscribe();

    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.resizeListener) {
      window.removeEventListener('resize', this.resizeListener);
    }

  }

  private initKrakenAnimation() {
    if (!this.krakenCanvas || !this.krakenCanvas.nativeElement) {
      console.warn('Kraken Canvas not found');
      return;
    }
    const canvas = this.krakenCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set sizing with High-DPI support to ensure crystal-clear rendering
    const resizeCanvas = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      const width = rect?.width || 260;
      const height = rect?.height || window.innerHeight;
      const dpr = window.devicePixelRatio || 1;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      
      ctx.scale(dpr, dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    };
    
    resizeCanvas();
    // ------------------------------------------------------------------------
    // VERGE KRAKEN - MAJESTIC FULL-SIDEBAR PROCEDURAL VECTOR ART
    // ------------------------------------------------------------------------
    
    let time = 0;

    const animate = () => {
      time += 0.015;
      const rect = canvas.parentElement?.getBoundingClientRect();
      const w = rect?.width || 260;
      const h = rect?.height || window.innerHeight || 900;

      ctx.clearRect(0, 0, w, h);

      // The Abyss - Deep glowing aura at the bottom
      const gradient = ctx.createRadialGradient(w / 2, h, 0, w / 2, h, 400);
      gradient.addColorStop(0, 'rgba(0, 243, 255, 0.05)');
      gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, w, h);

      ctx.save();
      ctx.strokeStyle = '#00f3ff';
      ctx.shadowColor = '#00f3ff';
      ctx.shadowBlur = 10;
      ctx.lineWidth = 1.2;
      ctx.globalAlpha = 0.25; // Subtle majestic opacity so it doesn't overpower text

      // Center the entity at the very bottom of the sidebar
      const centerX = w / 2;
      const centerY = h - 60; // Lowered significantly

      // --- 1. QUANTUM CYBER-CORE (The Abstract "Head") ---
      ctx.save();
      ctx.translate(centerX, centerY);
      
      // Outer spinning ring
      ctx.rotate(time * 0.4);
      ctx.beginPath();
      ctx.arc(0, 0, 35, 0, Math.PI * 1.6);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.2)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      
      // Inner spinning ring
      ctx.rotate(-time * 0.7);
      ctx.beginPath();
      ctx.arc(0, 0, 22, Math.PI * 0.4, Math.PI * 2.1);
      ctx.strokeStyle = 'rgba(0, 255, 136, 0.3)';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Central Energy Core (Pulsating Diamond)
      const pulse = Math.sin(time * 2.5) * 4;
      ctx.rotate(time * 0.2); // Slowly rotate the diamond
      ctx.beginPath();
      ctx.moveTo(0, -12 - pulse);
      ctx.lineTo(8 + pulse/2, 0);
      ctx.lineTo(0, 12 + pulse);
      ctx.lineTo(-8 - pulse/2, 0);
      ctx.closePath();
      ctx.fillStyle = '#00f3ff';
      ctx.shadowBlur = 15;
      ctx.shadowColor = '#00f3ff';
      ctx.fill();
      
      ctx.restore();

      // --- 2. ENERGY TENDRILS (Abstract Tentacles) ---
      // These tentacles reach UPWARDS across the entire sidebar menu!
      const numTentacles = 8;

      for (let i = 0; i < numTentacles; i++) {
        // Distribute base points in a semi-circle over the top of the core
        const tRatio = i / (numTentacles - 1); // 0.0 to 1.0
        const angle = Math.PI * 1.1 + (tRatio * Math.PI * 0.8);
        const baseX = centerX + Math.cos(angle) * 20;
        const baseY = centerY + Math.sin(angle) * 20;
        
        // Massive tentacles that span the height of the sidebar
        const tentacleLength = 350 + Math.sin(i * 456) * 200; 
        const segments = 45;
        
        const spreadDirection = (tRatio - 0.5) * 2; // -1 to 1

        const points = [{x: baseX, y: baseY}];
        
        for (let s = 1; s <= segments; s++) {
          const sRatio = s / segments;
          
          // Reaching upwards
          let currentY = baseY - sRatio * tentacleLength;
          
          // Complex sweeping organic waves
          const wave1 = Math.sin(time * 1.2 - sRatio * 3 + i) * 25 * sRatio;
          const wave2 = Math.cos(time * 0.7 - sRatio * 5 + i * 2) * 15 * sRatio;
          
          // Tentacles spread out, and curl organically
          const spread = spreadDirection * sRatio * 110; 
          const curl = Math.cos(time * 0.4 + i) * 60 * Math.pow(sRatio, 2); // Heavy curl at the tips
          
          let currentX = baseX + spread + wave1 + wave2 + curl;
          
          points.push({x: currentX, y: currentY});
        }
        
        // Draw the organic tapering spline in multiple layers for a neon-glow effect
        for (let p = 1; p < points.length; p++) {
           const p1 = points[p-1];
           const p2 = points[p];
           const taper = 1 - (p / points.length);
           
           // Core Bright Line
           ctx.beginPath();
           ctx.moveTo(p1.x, p1.y);
           ctx.lineTo(p2.x, p2.y);
           ctx.strokeStyle = '#00f3ff';
           ctx.globalAlpha = 0.5;
           ctx.lineWidth = 1.5 * taper;
           ctx.shadowBlur = 6;
           ctx.shadowColor = '#00f3ff';
           ctx.stroke();

           // Outer Energy Aura
           ctx.beginPath();
           ctx.moveTo(p1.x, p1.y);
           ctx.lineTo(p2.x, p2.y);
           ctx.strokeStyle = 'rgba(0, 243, 255, 0.15)';
           ctx.globalAlpha = 1.0;
           ctx.lineWidth = 8 * taper;
           ctx.shadowBlur = 0;
           ctx.stroke();
        }

        // Layer 3: Cyberpunk Data Packets traveling up the tendril
        const packetSpeed = 0.2 + (i % 3) * 0.05;
        const packetPos = (time * packetSpeed) % 1; 
        const pIndex = Math.floor(packetPos * (points.length - 1));
        
        if (pIndex >= 0 && pIndex < points.length - 1) {
            const p1 = points[pIndex];
            const p2 = points[pIndex + 1];
            const subRatio = (packetPos * (points.length - 1)) - pIndex;
            const px = p1.x + (p2.x - p1.x) * subRatio;
            const py = p1.y + (p2.y - p1.y) * subRatio;
            
            ctx.beginPath();
            ctx.arc(px, py, 2.0, 0, Math.PI * 2);
            ctx.fillStyle = '#00ff88'; // Matrix green data pulse
            ctx.shadowColor = '#00ff88';
            ctx.shadowBlur = 12;
            ctx.fill();
        }
      }

      ctx.restore();
      this.animationFrameId = requestAnimationFrame(animate);
    };

    this.animationFrameId = requestAnimationFrame(animate);


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
    if (url === '/' || url === '/home') {
      this.currentRouteName = 'DASHBOARD CORE';
    } else if (url === '/nexus-15') {
      this.currentRouteName = 'NEXUS-15 PREDICTIVE CORE';
    } else if (url === '/agent') {
      this.currentRouteName = 'AI TRADING AGENT';
    } else if (url === '/agent-audit') {
      this.currentRouteName = 'AUDITORÍA DE OPERACIONES';
    } else if (url.startsWith('/strategies')) {
      this.currentRouteName = 'ESTRATEGIAS DE INVERSIÓN';
    } else if (url === '/dashboard-advanced') {
      this.currentRouteName = 'POSICIONES ABIERTAS';
    } else if (url === '/history') {
      this.currentRouteName = 'HISTORIAL DE OPERACIONES';
    } else if (url === '/backtesting') {
      this.currentRouteName = 'BACKTESTING SIMULADO';
    } else if (url === '/alerts') {
      this.currentRouteName = 'ALERTAS DEL MERCADO';
    } else if (url === '/profile') {
      this.currentRouteName = 'CONFIGURACIÓN DEL SISTEMA';
    } else if (url.startsWith('/admin')) {
      this.currentRouteName = 'PANEL DE ADMINISTRACIÓN';
    } else {
      this.currentRouteName = 'VERGE INTELLIGENCE';
    }
  }

  private startTrackers() {
    // Reloj dinámico Buenos Aires (UTC-3)
    const updateClock = () => {
      const now = new Date();
      const options: Intl.DateTimeFormatOptions = {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: 'America/Argentina/Buenos_Aires'
      };
      this.currentTime = now.toLocaleTimeString('es-AR', options);
    };
    updateClock();
    this.clockTimer = setInterval(updateClock, 1000);

    // Latencia dinámica realista
    this.latencyTimer = setInterval(() => {
      this.latency = Math.floor(Math.random() * 9) + 14; // 14ms - 22ms
    }, 3000);

    // Uptime dinámico
    const updateUptime = () => {
      this.baseUptimeMinutes++;
      const days = Math.floor(this.baseUptimeMinutes / 1440);
      const hours = Math.floor((this.baseUptimeMinutes % 1440) / 60);
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
        if (msg && msg.data) {
          const symbol = msg.data.s;
          const price = parseFloat(msg.data.c);
          const pct = parseFloat(msg.data.P);
          
          const idx = this.tickers.findIndex(t => t.symbol === symbol);
          if (idx !== -1) {
            this.tickers[idx].price = price;
            this.tickers[idx].changePercent = pct;
            this.tickers[idx].change = pct >= 0 ? 1 : -1;
          }
        }
      };

      this.ws.onerror = (err) => {
        console.warn('[Layout Websocket] Error:', err);
      };

      this.ws.onclose = () => {
        setTimeout(() => {
          if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
            this.initWebsocket();
          }
        }, 5000);
      };
    } catch (e) {
      console.error('[Layout Websocket] Exception during init:', e);
    }
  }
}