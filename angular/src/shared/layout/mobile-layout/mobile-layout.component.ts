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
      notificationsOutline, settingsOutline, personOutline
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

  ngAfterViewInit() {
    setTimeout(() => {
      this.ngZone.runOutsideAngular(() => { this.initKrakenAnimation(); });
    }, 100);
  }

  ngOnDestroy() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    if (this.latencyTimer) clearInterval(this.latencyTimer);
    if (this.uptimeTimer) clearInterval(this.uptimeTimer);
    if (this.ws) { try { this.ws.close(); } catch (e) {} }
    this.routerSub?.unsubscribe();
    if (this.animationFrameId) cancelAnimationFrame(this.animationFrameId);
    if (this.resizeListener) window.removeEventListener('resize', this.resizeListener);
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // VERGE CORE — Institutional AI Entity
  // Philosophy: 95% stillness, 5% motion. Dangerous. Intelligent. Silent.
  // ─────────────────────────────────────────────────────────────────────────────
  private initKrakenAnimation() {
    if (!this.krakenCanvas?.nativeElement) return;
    const canvas = this.krakenCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = rect?.width || 260, h = rect?.height || 900;
      canvas.width = w * dpr; canvas.height = h * dpr;
      ctx.scale(dpr, dpr);
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    };
    resize();

    let t = 0;

    // Hex path helper
    const hex = (cx: number, cy: number, r: number, rot = 0) => {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = rot + (Math.PI / 3) * i;
        i === 0 ? ctx.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a))
                : ctx.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
      }
      ctx.closePath();
    };

    // Hex gear path helper — draws real mechanical gear teeth
    const gearHex = (cx: number, cy: number, r: number, rot = 0, teethCount = 18) => {
      ctx.beginPath();
      for (let i = 0; i < teethCount; i++) {
        const a = rot + (Math.PI * 2 / teethCount) * i;
        const nextA = rot + (Math.PI * 2 / teethCount) * (i + 0.5);
        const rCurrent = i % 2 === 0 ? r + 2.5 : r - 2;
        const rNext = i % 2 === 0 ? r + 2.5 : r - 2;
        const x1 = cx + rCurrent * Math.cos(a);
        const y1 = cy + rCurrent * Math.sin(a);
        const x2 = cx + rNext * Math.cos(nextA);
        const y2 = cy + rNext * Math.sin(nextA);
        if (i === 0) ctx.moveTo(x1, y1);
        else ctx.lineTo(x1, y1);
        ctx.lineTo(x2, y2);
      }
      ctx.closePath();
    };

    // Rhombus (Diamond) path helper
    const rhombus = (cx: number, cy: number, w: number, h: number, rot = 0) => {
      ctx.beginPath();
      for (let i = 0; i < 4; i++) {
        const a = rot + (Math.PI / 2) * i;
        const r = i % 2 === 0 ? w : h;
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      };

    // Mystical procedural alchemical/occult rune generator
    const drawRune = (cx: number, cy: number, size: number, seed: number) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.strokeStyle = '#00ffd2';
      ctx.lineWidth = 1.0;
      ctx.shadowColor = '#00e8ff'; ctx.shadowBlur = 4;
      ctx.beginPath();
      
      // Generate a unique alchemical shape based on the seed
      const type = seed % 4;
      if (type === 0) {
        // Circle with vertical bar and cross (Alchemical Mercury-like symbol)
        ctx.arc(0, -size * 0.2, size * 0.3, 0, Math.PI * 2);
        ctx.moveTo(0, size * 0.1);
        ctx.lineTo(0, size * 0.6);
        ctx.moveTo(-size * 0.2, size * 0.35);
        ctx.lineTo(size * 0.2, size * 0.35);
      } else if (type === 1) {
        // Triangle with horizontal bar (Alchemical Earth/Air symbol)
        ctx.moveTo(0, -size * 0.5);
        ctx.lineTo(-size * 0.4, size * 0.4);
        ctx.lineTo(size * 0.4, size * 0.4);
        ctx.closePath();
        ctx.moveTo(-size * 0.3, 0);
        ctx.lineTo(size * 0.3, 0);
      } else if (type === 2) {
        // Crossed lines with double alchemical dots (occult summon seal)
        ctx.moveTo(-size * 0.4, -size * 0.4);
        ctx.lineTo(size * 0.4, size * 0.4);
        ctx.moveTo(size * 0.4, -size * 0.4);
        ctx.lineTo(-size * 0.4, size * 0.4);
        // tiny circle on top
        ctx.moveTo(0, -size * 0.4);
        ctx.arc(0, -size * 0.4, size * 0.1, 0, Math.PI * 2);
      } else {
        // Alchemical sulfur (Triangle over cross)
        ctx.moveTo(0, -size * 0.4);
        ctx.lineTo(-size * 0.3, size * 0.1);
        ctx.lineTo(size * 0.3, size * 0.1);
        ctx.closePath();
        ctx.moveTo(0, size * 0.1);
        ctx.lineTo(0, size * 0.6);
        ctx.moveTo(-size * 0.2, size * 0.35);
        ctx.lineTo(size * 0.2, size * 0.35);
      }
      ctx.stroke();
      ctx.restore();
    };

    // Golden Fibonacci Spiral path helper (Phi Spiral)
    const drawPhiSpiral = (cx: number, cy: number, maxR: number, rot = 0) => {
      ctx.beginPath();
      let r = 0.5;
      let theta = 0;
      const b = 0.3063489; // Golden spiral factor
      const a = 1.0;
      ctx.moveTo(cx, cy);
      for (let i = 0; i < 110; i++) {
        theta = i * 0.12;
        r = a * Math.exp(b * theta);
        if (r > maxR) break;
        const x = cx + r * Math.cos(theta + rot);
        const y = cy + r * Math.sin(theta + rot);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
    };

    // Smooth bezier spline
    const spline = (pts: {x:number;y:number}[]) => {
      if (pts.length < 2) return;
      ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length - 1; i++)
        ctx.quadraticCurveTo(pts[i].x, pts[i].y, (pts[i].x+pts[i+1].x)/2, (pts[i].y+pts[i+1].y)/2);
      const l = pts.length - 1;
      ctx.quadraticCurveTo(pts[l-1].x, pts[l-1].y, pts[l].x, pts[l].y);
    };

    // Sparse proximity particles
    const orbs = Array.from({length: 18}, (_, i) => ({
      ox: Math.random() * 260,
      oy: Math.random() * 900,
      r: 0.5 + Math.random() * 1.2,
      spd: 0.08 + Math.random() * 0.14,
      ph: Math.random() * Math.PI * 2,
      col: i % 4 === 0 ? '#00ff88' : '#00f3ff'
    }));

    // ── NEURAL PROCESS SYSTEM ────────────────────────────────────────────────
    // Each node is an independent process with its own lifecycle.
    // States: 0=dormant  1=thinking  2=firing  3=refractory
    // No two nodes share the same rhythm → sense of individuality / thought
    interface NNode {
      angle: number;      // position around core (radians)
      dist: number;       // distance from core center
      freq: number;       // personal oscillation frequency
      ph: number;         // phase offset — desynchronizes each node
      state: number;      // 0 dormant | 1 thinking | 2 firing | 3 refractory
      activity: number;   // current activity level 0..1
      stateTimer: number; // how long in current state (in t-units)
      connects: number[]; // indices of nodes this one can signal
      signal: { active: boolean; target: number; progress: number; } ;
    }
    const N = 9;
    const nodes: NNode[] = Array.from({length: N}, (_, i) => {
      // Golden Ratio Nested Orbits: scaled down by 50% to [24, 38, 60]
      const phiOrbits = [24, 38, 60];
      return {
        angle:   (Math.PI * 2 / N) * i + Math.random() * 0.2,
        dist:    phiOrbits[i % 3],
        freq:    0.18 + Math.random() * 0.32,   // each is unique
        ph:      Math.random() * Math.PI * 2,    // fully desynchronized
        state:   0,
        activity: Math.random() * 0.15,
        stateTimer: Math.random() * 8,
        connects: [(i + 1 + Math.floor(Math.random() * 2)) % N, (i + N - 1) % N],
        signal: { active: false, target: 0, progress: 0 }
      };
    });

    // State machine update (called once per frame per node)
    const updateNode = (n: NNode, dt: number) => {
      n.stateTimer += dt;
      if (n.state === 0) {           // dormant — slowly oscillate, rarely wake
        n.activity = 0.05 + 0.08 * Math.abs(Math.sin(n.freq * n.stateTimer + n.ph));
        if (n.stateTimer > (6 + Math.random() * 10)) { n.state = 1; n.stateTimer = 0; }
      } else if (n.state === 1) {    // thinking — activity builds
        n.activity = Math.min(1, n.activity + dt * 0.8);
        if (n.stateTimer > (1.5 + Math.random() * 2.5)) { n.state = 2; n.stateTimer = 0; }
      } else if (n.state === 2) {    // firing — peak brightness, send signal
        n.activity = 0.85 + 0.15 * Math.sin(n.stateTimer * 12);
        if (!n.signal.active) {
          n.signal.active = true;
          n.signal.target = n.connects[Math.floor(Math.random() * n.connects.length)];
          n.signal.progress = 0;
        }
        if (n.stateTimer > 0.6) { n.state = 3; n.stateTimer = 0; }
      } else {                       // refractory — cools down
        n.activity = Math.max(0.05, n.activity - dt * 0.5);
        if (n.stateTimer > (2 + Math.random() * 3)) { n.state = 0; n.stateTimer = 0; }
      }
      // Advance signal
      if (n.signal.active) {
        n.signal.progress += dt * 1.2;
        if (n.signal.progress >= 1) {
          // Trigger target node into thinking state
          const tgt = nodes[n.signal.target];
          if (tgt.state === 0) { tgt.state = 1; tgt.stateTimer = 0; }
          n.signal.active = false; n.signal.progress = 0;
        }
      }
    };


    const loop = () => {
      t += 0.004; // 95% stillness — institutional / quant feel
      const rect = canvas.parentElement?.getBoundingClientRect();
      const W = rect?.width || 260, H = rect?.height || 900;

      ctx.clearRect(0, 0, W, H);

      const cX = W / 2, cY = H * 0.81, R = 17;
      const breath = Math.sin(t * 0.8);       // ~7s full cycle
      const bAmt   = breath * 0.5 + 0.5;      // normalized 0..1

      // ── DIGITAL DEPTH ATMOSPHERE ─────────────────────────────────────────────
      const smoke = ctx.createRadialGradient(cX, cY + 5, 0, cX, cY + 5, 75);
      smoke.addColorStop(0, `rgba(0,40,60,${0.06 + bAmt * 0.03})`);
      smoke.addColorStop(0.6, 'rgba(0,20,35,0.025)');
      smoke.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = smoke; ctx.fillRect(0, 0, W, H);

      // ── RADIAL NEURAL TENTACLES (360-degree organic dispersion) ─────────────
      // 8 majestic tentacles radiating outward in all directions, waving like an organic entity.
      // Opacity fades out beautifully near the tips so they dissolve into the darkness.
      const tentacleCount = 8;
      const tentacleLength = 80; // Compressed to 80px (50% size)
      const steps = 80; // High resolution for silky smooth LERP travel

      for (let i = 0; i < tentacleCount; i++) {
        // 360-degree split (every 45 degrees)
        const baseAngle = (Math.PI * 2 / tentacleCount) * i;
        
        const pts: {x: number; y: number}[] = [];
        for (let s = 0; s <= steps; s++) {
          const ratio = s / steps;
          const dist = R + ratio * tentacleLength;

          // Wave alters the angle (angular wiggle perpendicular to growth)
          const waveAmp = ratio * 0.22; // 0 base, ~12 degrees sway at the tip
          const wave = Math.sin(t * 2.0 - ratio * 5.0 + i * 1.5) * waveAmp;

          // Subtle organic breathing length expansion/contraction
          const pulse = 1.0 + Math.sin(t * 1.2 + i * 0.8) * 0.05;

          pts.push({
            x: cX + Math.cos(baseAngle + wave) * (dist * pulse),
            y: cY + Math.sin(baseAngle + wave) * (dist * pulse)
          });
        }

        ctx.save();
        // Delicate opacity that dissolves to 0 at the tip
        ctx.globalAlpha = 0.09 + Math.sin(t * 0.18 + i) * 0.03;
        
        // Dynamic color gradient: starts bright cian/teal near core, fades to soft dark cian
        const grad = ctx.createRadialGradient(cX, cY, R, cX, cY, R + tentacleLength);
        grad.addColorStop(0, i % 2 === 0 ? '#00f3ff' : '#00ff88');
        grad.addColorStop(0.5, i % 2 === 0 ? 'rgba(0,200,255,0.6)' : 'rgba(0,255,160,0.5)');
        grad.addColorStop(1, 'rgba(0,100,150,0)');

        ctx.strokeStyle = grad;
        ctx.lineWidth = 0.80;
        ctx.shadowColor = i % 2 === 0 ? '#00f3ff' : '#00ff88';
        ctx.shadowBlur = 3;

        // Draw smooth waving tentacle polyline
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let s = 1; s < pts.length; s++) {
          ctx.lineTo(pts[s].x, pts[s].y);
        }
        ctx.stroke();

        // Traveling data packets moving OUTWARD along the tentacles
        const packetSpd = 0.05 + (i % 3) * 0.015;
        const progress = ((t * packetSpd + i * 0.25) % 1.0);

        // Mathematically perfect LERP over the radial path (zero-jump flow)
        const floatIdx = progress * (pts.length - 1);
        const idxA = Math.floor(floatIdx);
        const idxB = Math.min(pts.length - 1, idxA + 1);
        const lerpRatio = floatIdx - idxA;

        const ptA = pts[idxA];
        const ptB = pts[idxB];
        if (ptA && ptB) {
          const px = ptA.x + (ptB.x - ptA.x) * lerpRatio;
          const py = ptA.y + (ptB.y - ptA.y) * lerpRatio;

          // Packet fades out towards the tip as it transmits signal
          ctx.globalAlpha = 0.70 * (1.0 - progress);
          ctx.fillStyle = i % 2 === 0 ? '#00ff88' : '#00e8ff';
          ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(px, py, 2.0, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      // ── NEURAL PROCESSES — independent execution units ────────────────────
      const dt = 0.004;
      nodes.forEach(n => updateNode(n, dt));
      const totalActivity = nodes.reduce((s,n) => s + n.activity, 0) / nodes.length;
      const orbitR = R + 11 + bAmt * 0.9; // Radius of the rotating outer highway (scaled by 50%)

      nodes.forEach((n, i) => {
        // Planetary gear rotation: all neural ports revolve slowly around the main axis
        const activeAngle = n.angle + t * 0.06;
        const nx = cX + Math.cos(activeAngle) * n.dist;
        const ny = cY + Math.sin(activeAngle) * n.dist;

        // Synapse arcs to connected nodes via the rotating hex highway
        n.connects.forEach(ci => {
          const cn = nodes[ci];
          const cnAngle = cn.angle + t * 0.06;
          const cnx = cX + Math.cos(cnAngle) * cn.dist;
          const cny = cY + Math.sin(cnAngle) * cn.dist;
          const sa = (n.activity + cn.activity) * 0.04;
          if (sa < 0.01) return;

          // Angles of source and target nodes relative to core center
          const angleA = Math.atan2(ny - cY, nx - cX);
          const angleB = Math.atan2(cny - cY, cnx - cX);

          // Render Synapse Highway in Cyberpunk Turquoise
          ctx.save();
          ctx.globalAlpha = Math.min(0.22, sa);
          ctx.strokeStyle = 'rgba(0, 243, 255, 0.4)'; ctx.shadowColor = '#00e8ff'; ctx.shadowBlur = 4;
          ctx.lineWidth = 0.45; ctx.lineCap = 'round';

          ctx.beginPath();
          // 1. Line from Source Node to Outer Orbit
          ctx.moveTo(nx, ny);
          const oxA = cX + Math.cos(angleA) * orbitR;
          const oyA = cY + Math.sin(angleA) * orbitR;
          ctx.lineTo(oxA, oyA);

          // 2. Arc along the Orbit Highway (shortest path)
          let diff = angleB - angleA;
          while (diff < -Math.PI) diff += Math.PI * 2;
          while (diff > Math.PI) diff -= Math.PI * 2;
          ctx.arc(cX, cY, orbitR, angleA, angleA + diff, diff < 0);

          // 3. Line from Outer Orbit to Target Node
          ctx.lineTo(cnx, cny);
          ctx.stroke();

          // Signal pulse traveling along the highway
          if (n.signal.active && n.signal.target === ci) {
            const p = n.signal.progress; // 0..1
            let px = 0, py = 0;
            const oxB = cX + Math.cos(angleB) * orbitR;
            const oyB = cY + Math.sin(angleB) * orbitR;

            if (p < 0.25) {
              // Stage 1: Get onto the highway (Node -> Orbit)
              const s1 = p / 0.25;
              px = nx + (oxA - nx) * s1;
              py = ny + (oyA - ny) * s1;
            } else if (p <= 0.75) {
              // Stage 2: Ride the rotating highway (Along Orbit)
              const s2 = (p - 0.25) / 0.50;
              const currentAngle = angleA + diff * s2;
              px = cX + Math.cos(currentAngle) * orbitR;
              py = cY + Math.sin(currentAngle) * orbitR;
            } else {
              // Stage 3: Branch off to target port (Orbit -> Node)
              const s3 = (p - 0.75) / 0.25;
              px = oxB + (cnx - oxB) * s3;
              py = oyB + (cny - oyB) * s3;
            }

            ctx.globalAlpha = 0.90;
            ctx.fillStyle = n.state === 2 ? '#00ffd2' : '#00f3ff';
            ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 10;
            ctx.beginPath(); ctx.arc(px, py, 2.2, 0, Math.PI * 2); ctx.fill();
            ctx.globalAlpha = 0.32; ctx.shadowBlur = 6;
            ctx.beginPath(); ctx.arc(px, py, 3.8, 0, Math.PI * 2); ctx.fill();
          }
          ctx.restore();
        });

        // Node dot in Cyberpunk Turquoise/Cyan
        const col = n.state === 2 ? '#00ffd2' : n.state === 1 ? '#00f3ff' : n.state === 3 ? '#0088aa' : '#002430';
        const nR = 1.2 + n.activity * 2.4;
        ctx.save();
        ctx.globalAlpha = 0.15 + n.activity * 0.70;
        ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 4 + n.activity * 14;
        ctx.beginPath(); ctx.arc(nx, ny, nR, 0, Math.PI * 2); ctx.fill();
        if (n.state >= 1) {
          ctx.globalAlpha = n.activity * 0.35; ctx.strokeStyle = col; ctx.lineWidth = 0.6;
          ctx.beginPath(); ctx.arc(nx, ny, nR + 3, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.globalAlpha = n.activity * 0.08; ctx.strokeStyle = '#00f3ff';
        ctx.lineWidth = 0.3; ctx.shadowBlur = 0;
        ctx.beginPath(); ctx.moveTo(nx, ny); ctx.lineTo(cX, cY); ctx.stroke();
        ctx.restore();
      });

      // ── VERGE CORE ENTITY — ALCHEMICAL SUMMONING REACTOR ────────────────────
      const neuralLoad = totalActivity;
      ctx.save(); ctx.translate(cX, cY);

      // Outer diffuse alchemical turquoise corona (cyberpunk glow)
      const corona = ctx.createRadialGradient(0, 0, R, 0, 0, R * 3.5);
      corona.addColorStop(0, `rgba(0, 243, 255, ${0.045 + bAmt * 0.035})`);
      corona.addColorStop(0.5, 'rgba(0, 255, 210, 0.015)');
      corona.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = corona;
      ctx.beginPath(); ctx.arc(0, 0, R * 3.5, 0, Math.PI * 2); ctx.fill();

      // Outer golden/neon summon hexagon (sharp mockup anchor)
      ctx.save(); ctx.rotate(t * 0.04);
      hex(0, 0, orbitR + 2, 0);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.32)'; ctx.lineWidth = 0.85;
      ctx.shadowColor = '#00f3ff'; ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.restore();

      // Outer alchemical summoning ring with 16 rotating runes
      ctx.save(); ctx.rotate(t * 0.08);
      ctx.beginPath(); ctx.arc(0, 0, orbitR + 2, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.25)'; ctx.lineWidth = 0.85;
      ctx.stroke();

      for (let r = 0; r < 16; r++) {
        const angle = (Math.PI * 2 / 16) * r;
        const rx = Math.cos(angle) * (orbitR + 2);
        const ry = Math.sin(angle) * (orbitR + 2);
        ctx.save();
        ctx.translate(rx, ry);
        ctx.rotate(angle + Math.PI / 2);
        drawRune(0, 0, 4.5, r + 9);
        ctx.restore();
      }
      ctx.restore();

      // Three Major Runic summon seals (distributed at 0, 120, 240 degrees)
      ctx.save(); ctx.rotate(t * 0.05);
      for (let i = 0; i < 3; i++) {
        const angle = (Math.PI * 2 / 3) * i;
        const nx = Math.cos(angle) * orbitR;
        const ny = Math.sin(angle) * orbitR;
        
        ctx.beginPath(); ctx.arc(nx, ny, 7.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(0, 20, 30, 0.9)';
        ctx.strokeStyle = '#00ffd2'; ctx.lineWidth = 1.0;
        ctx.shadowColor = '#00e8ff'; ctx.shadowBlur = 8;
        ctx.fill(); ctx.stroke();

        drawRune(nx, ny, 4.0, i * 3 + 5);
      }
      ctx.restore();

      // Intersecting Solomon Triangles (Glowing Hexagram alchemical grid in the core)
      ctx.save();
      // Triangle 1 (pointing up)
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const a = (Math.PI * 2 / 3) * i - Math.PI / 2 - t * 0.04;
        const x = R * 0.95 * Math.cos(a);
        const y = R * 0.95 * Math.sin(a);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.28)'; ctx.lineWidth = 0.85;
      ctx.stroke();

      // Triangle 2 (pointing down, rotated 180 degrees)
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const a = (Math.PI * 2 / 3) * i + Math.PI / 2 - t * 0.04;
        const x = R * 0.95 * Math.cos(a);
        const y = R * 0.95 * Math.sin(a);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(0, 255, 210, 0.24)'; ctx.lineWidth = 0.85;
      ctx.stroke();
      ctx.restore();

      // Ring 3: Outer thin Bezel ring with specular highlight
      ctx.save();
      ctx.beginPath(); ctx.arc(0, 0, R * 1.05, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.40)'; ctx.lineWidth = 1.8;
      ctx.stroke();
      // specular gloss highlight on Bezel ring
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.45)'; ctx.lineWidth = 0.85;
      ctx.beginPath(); ctx.arc(0, 0, R * 1.05, -Math.PI * 0.7, -Math.PI * 0.3);
      ctx.stroke();
      ctx.restore();

      // Ring 2: Thick alchemical dial with segmented ruins (rotates counter-clockwise)
      ctx.save(); ctx.rotate(-t * 0.06);
      ctx.beginPath(); ctx.arc(0, 0, R * 0.85, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.22)'; ctx.lineWidth = 3.5;
      ctx.stroke();
      
      // Segmented glowing dial tracks
      ctx.strokeStyle = '#00ffd2'; ctx.lineWidth = 1.2; ctx.shadowColor = '#00f3ff'; ctx.shadowBlur = 6;
      ctx.beginPath(); ctx.arc(0, 0, R * 0.85, 0, Math.PI * 2);
      ctx.setLineDash([6, 12]);
      ctx.stroke();
      ctx.restore();

      // Ring 1: Inner solid circular track
      ctx.save();
      ctx.beginPath(); ctx.arc(0, 0, R * 0.65, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.32)'; ctx.lineWidth = 1.8;
      ctx.stroke();
      ctx.restore();

      // Glossy Black Occult Sphere (Core body)
      ctx.beginPath(); ctx.arc(0, 0, R * 0.60, 0, Math.PI * 2);
      const bodyG = ctx.createRadialGradient(-R * 0.18, -R * 0.20, 1.0, 0, 0, R * 0.60);
      bodyG.addColorStop(0, 'rgba(0, 20, 30, 0.98)');
      bodyG.addColorStop(0.5, 'rgba(0, 10, 15, 0.97)');
      bodyG.addColorStop(1, 'rgba(0, 4, 8, 0.94)');
      ctx.fillStyle = bodyG;
      ctx.shadowColor = '#00e8ff'; ctx.shadowBlur = 10 + bAmt * 5;
      ctx.fill();

      // ── STYLIZED CYBERPUNK CRYPTO COIN GLYPH (ETH-like dual pyramids with central quantum halo) ──
      const sigRadius = R * 0.48;
      ctx.save();
      ctx.rotate(t * 0.10); // elegant slow rotation
      ctx.strokeStyle = '#00ffd2'; // cyberpunk turquoise
      ctx.lineWidth = 1.65;
      ctx.shadowColor = '#00f3ff'; ctx.shadowBlur = 10 + neuralLoad * 12;
      
      // Top pyramid (glowing cyber ETH octahedron upper half)
      ctx.beginPath();
      ctx.moveTo(0, -sigRadius * 0.85);
      ctx.lineTo(-sigRadius * 0.45, -sigRadius * 0.10);
      ctx.lineTo(sigRadius * 0.45, -sigRadius * 0.10);
      ctx.closePath();
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(0, -sigRadius * 0.85);
      ctx.lineTo(0, -sigRadius * 0.10);
      ctx.stroke();

      // Bottom pyramid (glowing cyber ETH octahedron lower half)
      ctx.beginPath();
      ctx.moveTo(0, sigRadius * 0.85);
      ctx.lineTo(-sigRadius * 0.45, sigRadius * 0.10);
      ctx.lineTo(sigRadius * 0.45, sigRadius * 0.10);
      ctx.closePath();
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(0, sigRadius * 0.85);
      ctx.lineTo(0, sigRadius * 0.10);
      ctx.stroke();

      // Central quantum halo slice
      ctx.beginPath();
      ctx.ellipse(0, 0, sigRadius * 0.65, sigRadius * 0.18, 0, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.85)';
      ctx.lineWidth = 1.2;
      ctx.stroke();

      // Glowing core quantum light dot in center
      ctx.beginPath(); ctx.arc(0, 0, 2.2, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff'; ctx.shadowColor = '#00f3ff'; ctx.shadowBlur = 8;
      ctx.fill();
      ctx.restore();

      // Specular glass shine (Top-left specular light reflection)
      ctx.beginPath(); ctx.arc(0, 0, R * 0.60, 0, Math.PI * 2);
      const spec = ctx.createRadialGradient(-R*0.20, -R*0.22, 0.4, -R*0.06, -R*0.06, R*0.35);
      spec.addColorStop(0, `rgba(160, 250, 255, ${0.075 + bAmt * 0.025})`);
      spec.addColorStop(0.6, 'rgba(60, 210, 240, 0.012)');
      spec.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = spec; ctx.fill();

      // ── ANCHOR BOTTOM DIAMOND (Under the hexagon in Cyber Turquoise) ──────────────
      ctx.save();
      const anchorY = orbitR * 1.25;
      ctx.globalAlpha = 0.50 + bAmt * 0.35;
      ctx.fillStyle = '#00ffd2'; ctx.shadowColor = '#00e8ff'; ctx.shadowBlur = 8;
      rhombus(0, anchorY, 4.5, 7.5, 0);
      ctx.fill();
      ctx.restore();

      ctx.restore(); // end translate

      // ── PROXIMITY PARTICLES — sparse digital dust near core only ─────────────
      orbs.forEach(o => {
        const ox  = o.ox + Math.sin(t * o.spd + o.ph) * 9;
        const oy  = ((o.oy - t * 2.2) % H + H) % H;
        const dist = Math.sqrt((ox - cX) ** 2 + (oy - cY) ** 2);
        if (dist > 130) return; // only render near core
        const prox = 1 - dist / 130;
        ctx.save();
        ctx.globalAlpha = (0.08 + 0.12 * Math.abs(Math.sin(t * 0.6 + o.ph))) * prox;
        ctx.fillStyle = o.col;
        ctx.shadowColor = o.col; ctx.shadowBlur = 3;
        ctx.beginPath(); ctx.arc(ox, oy, o.r * 0.5, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      });

      this.animationFrameId = requestAnimationFrame(loop);
    };

    this.animationFrameId = requestAnimationFrame(loop);
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