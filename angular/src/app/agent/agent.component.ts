import { Component, OnInit, OnDestroy, inject, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { IonIcon } from '@ionic/angular/standalone';
import { AgentService } from '../proxy/agent/agent.service';
import { AgentSignalrService, AgentLog } from './agent-signalr.service';
import { Subscription } from 'rxjs';

export type SystemState = 'STOPPED' | 'STARTING_SERVER' | 'SERVER_READY' | 'AGENT_RUNNING';

@Component({
  selector: 'app-agent',
  standalone: true,
  imports: [CommonModule, IonIcon, RouterLink],
  templateUrl: './agent.component.html',
  styleUrls: ['./agent.component.scss']
})
export class AgentComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('terminalContainer') private terminalContainer!: ElementRef;

  // State Machine
  systemState: SystemState = 'STOPPED';

  // Control Panel
  uptime = '00:00:00';
  startTime = '-';
  
  services = [
    { name: 'Binance (Futures)', key: 'binance' },
    { name: 'Bybit (Futures)', key: 'bybit' },
    { name: 'OKX (Futures)', key: 'okx' },
    { name: 'Bitget (Futures)', key: 'bitget' },
    { name: 'Pyth Network (Oracle)', key: 'pyth' },
    { name: 'Motor de Predicción', key: 'nexus' },
    { name: 'SCAR Signal Engine', key: 'scar' }
  ];

  // Store real-time exchange status from health check
  private exchangeStats: any = null;

  // Terminal Logs
  terminalLogs: { time: string, text: string, highlight?: boolean, color?: string }[] = [];
  
  private uptimeInterval: any;
  private startTimestamp: number = 0;

  // Performance General
  balance = '0.00';
  winRate = '0.0%';
  trades = 0;
  pnlTotal = '0.00';
  
  // Strategy Analysis
  scarStats = { winRate: '0.0%', pnl: '0.00', trades: 0, promWin: '0.00', promLoss: '0.00' };
  nexusStats = { winRate: '0.0%', pnl: '0.00', trades: 0, promWin: '0.00', promLoss: '0.00' };
  confluenceStats = { winRate: '0.0%', pnl: '0.00', trades: 0, promWin: '0.00', promLoss: '0.00' };
  tpslStats = { effectiveness: '0.0%', trades: 0, tpRate: '0.0%', slRate: '0.0%', rr: '0.00' };

  // Top Performers
  topSymbols: any[] = [];

  // Recent Operations
  operations: any[] = [];
  openPositions: any[] = [];

  private refreshInterval: any;
  private isRefreshing = false;

  private agentService = inject(AgentService);
  private agentSignalrService = inject(AgentSignalrService);
  private subscriptions = new Subscription();
  /** Market WS vía Docker/red: evita duplicar el bloque de logs sintéticos. */
  private dockerTerminalSeeded = false;
  private statePollHandle: ReturnType<typeof setInterval> | null = null;

  constructor() { }

  ngOnInit(): void {
    this.addLog('Sistema inicializado. Sincronizando estado...', '#64748b');

    // 1. Connect to SignalR immediately to receive any ongoing logs
    this.agentSignalrService.startConnection().then(() => {
      this.addLog('✅ Conectado al hub de señales.', '#10b981');
    }).catch(err => {
      console.error('Error connecting to SignalR:', err);
    });

    // 2. Sync state on load (Fix for F5) + reintento si Docker aún no respondía
    this.agentService.getSystemState().subscribe({
      next: (data: any) => {
        const state = this.normalizeAgentState(data?.state);
        this.applySyncedState(data, state);
        if (state === 'STOPPED') {
          this.startPollingUntilServerReady();
        }
      },
      error: (err) => {
        this.addLog('⚠️ No se pudo sincronizar el estado inicial con el servidor.', '#f59e0b');
        console.error('Error syncing state:', err);
        this.startPollingUntilServerReady();
      }
    });

    // 3. Initial data refresh (includes health via backend)
    this.refreshData();

    this.subscriptions.add(
      this.agentSignalrService.logs$.subscribe((log: AgentLog) => {
        this.addLog(log.message, log.color);
      })
    );

    this.subscriptions.add(
      this.agentSignalrService.state$.subscribe((state: any) => {
        const s = this.normalizeAgentState(state);
        this.systemState = s;
        if (s === 'STOPPED') {
          this.dockerTerminalSeeded = false;
          this.seenDockerLogs.clear();
          this.stopUptime();
          this.stopDataRefresh();
        }
        if (s === 'SERVER_READY' || s === 'AGENT_RUNNING') {
          if (!this.uptimeInterval) {
            if (!this.startTimestamp) {
              this.startTimestamp = Date.now();
            }
            this.startUptime();
            this.startDataRefresh();
          }
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.stopStatePolling();
    this.subscriptions.unsubscribe();
    this.stopUptime();
    this.stopDataRefresh();
    this.agentSignalrService.stopConnection();
  }

  private normalizeAgentState(raw: unknown): SystemState {
    const s = String(raw ?? '')
      .trim()
      .toUpperCase()
      .replace(/-/g, '_');
    if (s === 'STOPPED' || s === 'STARTING_SERVER' || s === 'SERVER_READY' || s === 'AGENT_RUNNING') {
      return s as SystemState;
    }
    return 'STOPPED';
  }

  /** Aplica estado del API (getSystemState) y arranca uptime/refresh si corresponde. */
  private applySyncedState(data: any, state: SystemState): void {
    this.systemState = state;

    if (state === 'STOPPED') {
      this.dockerTerminalSeeded = false;
      this.seenDockerLogs.clear();
      return;
    }

    this.addLog(`✅ Sistema detectado en ejecución: ${state}`, '#10b981');

    if (data?.startTime) {
      this.startTimestamp = new Date(data.startTime).getTime();
      this.startTime = `Iniciado ${new Date(data.startTime).toLocaleTimeString()}`;
    } else if (!this.startTimestamp) {
      this.startTimestamp = Date.now();
      this.startTime = `Hoy ${this.getCurrentTime()}`;
    }

    if (data?.marketWsExternal && (data?.health || data?.logs)) {
      this.maybeSeedDockerMarketWsLogs(data);
    }

    this.startUptime();
    this.startDataRefresh();
  }

  private startPollingUntilServerReady(): void {
    if (this.statePollHandle != null) {
      return;
    }
    let attempts = 0;
    const maxAttempts = 48;
    this.statePollHandle = setInterval(() => {
      attempts++;
      if (attempts > maxAttempts || this.systemState !== 'STOPPED') {
        this.stopStatePolling();
        return;
      }
      this.agentService.getSystemState().subscribe({
        next: (data: any) => {
          const st = this.normalizeAgentState(data?.state);
          if (st !== 'STOPPED') {
            this.applySyncedState(data, st);
            this.stopStatePolling();
          }
        },
        error: () => { /* seguir intentando */ }
      });
    }, 2500);
  }

  private stopStatePolling(): void {
    if (this.statePollHandle != null) {
      clearInterval(this.statePollHandle);
      this.statePollHandle = null;
    }
  }

  private seenDockerLogs = new Set<string>();

  private maybeSeedDockerMarketWsLogs(data: any): void {
    if (data?.logs && Array.isArray(data.logs)) {
      data.logs.forEach((logLine: string) => {
        if (!this.seenDockerLogs.has(logLine)) {
          this.seenDockerLogs.add(logLine);
          this.addLog(logLine, '#cbd5e1');
        }
      });
      // Mantener tamaño del Set para no perder memoria
      if (this.seenDockerLogs.size > 2000) {
        const arr = Array.from(this.seenDockerLogs).slice(-1000);
        this.seenDockerLogs = new Set(arr);
      }
    } else {
      if (this.dockerTerminalSeeded) {
        return;
      }
      this.dockerTerminalSeeded = true;
      this.addLog('═══════════════════════════════════════════════════════════════', '#64748b');
      this.addLog('  VERGE Market Data Service — resumen vía Docker/red (GET /health)', '#3b82f6');
      const health = data?.health;
      const exchanges = (health as any)?.exchanges as Record<string, { connected?: boolean; reconnects?: number }> | undefined;
      if (exchanges && typeof exchanges === 'object') {
        for (const name of Object.keys(exchanges)) {
          const v = exchanges[name];
          const ok = v?.connected === true;
          this.addLog(
            `  [WS:${name}] ${ok ? 'Connected' : 'Disconnected'}${v?.reconnects ? ` (reconnects=${v.reconnects})` : ''}`,
            ok ? '#10b981' : '#f59e0b'
          );
        }
      } else {
        this.addLog('  (Sin detalle exchanges en health; servicios marcados ACTIVO por estado online.)', '#94a3b8');
      }
      this.addLog('  HTTP Market WS operativo. Podés iniciar el agente.', '#10b981');
      this.addLog('═══════════════════════════════════════════════════════════════', '#64748b');
    }
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      const element = this.terminalContainer.nativeElement;
      const threshold = 100; // pixels from bottom to consider "at the end"
      const isAtBottom = element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
      
      // Only force scroll if they were already near the bottom
      if (isAtBottom) {
        element.scrollTop = element.scrollHeight;
      }
    } catch (err) { }
  }

  // --- Data Fetching ---

  private startDataRefresh() {
    this.stopDataRefresh();
    this.refreshData();
    this.refreshInterval = setInterval(() => this.refreshData(), 5000);
  }

  private stopDataRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  refreshData() {
    if (this.isRefreshing) {
      return;
    }
    this.isRefreshing = true;

    // Refresh backend state; backend is source of truth for MarketWS health.
    this.agentService.getSystemState().subscribe((data: any) => {
      if (data?.health) {
        this.exchangeStats = data.health;
      } else if (data?.isServerHealthy === false) {
        this.exchangeStats = null;
      }

      if (data?.state) {
        const st = this.normalizeAgentState(data.state);
        this.systemState = st;
        if (st === 'STOPPED') {
          this.dockerTerminalSeeded = false;
          this.seenDockerLogs.clear();
        }
        if (st === 'SERVER_READY' && data?.marketWsExternal && (data?.health || data?.logs)) {
          this.maybeSeedDockerMarketWsLogs(data);
        }
      }
    }, () => {
      // Keep previous telemetry on transient failures.
    }, () => {
      this.isRefreshing = false;
    });

    this.agentService.getAuditSummary().subscribe((data: any) => {
      if (data) {
        this.balance = data.balance?.toLocaleString('en-US') || '0.00';
        this.winRate = (data.winRate || 0) + '%';
        this.trades = data.trades || 0;
        this.pnlTotal = (data.pnlTotal > 0 ? '+' : '') + (data.pnlTotal || 0).toLocaleString('en-US');
      }
    });

    this.agentService.getStrategyStats().subscribe((data: any) => {
      if (data) {
        const formatStat = (s: any) => ({
          winRate: (s.winRate || 0) + '%',
          pnl: (s.pnl > 0 ? '+' : '') + (s.pnl || 0),
          trades: s.trades || 0,
          promWin: '+' + (s.promWin || 0),
          promLoss: (s.promLoss || 0).toString()
        });
        
        if (data.scar) this.scarStats = formatStat(data.scar);
        if (data.nexus) this.nexusStats = formatStat(data.nexus);
        if (data.confluence) this.confluenceStats = formatStat(data.confluence);
        if (data.tpsl) {
          this.tpslStats = {
            effectiveness: (data.tpsl.effectiveness || 0) + '%',
            trades: data.tpsl.trades || 0,
            tpRate: (data.tpsl.tpRate || 0) + '%',
            slRate: (data.tpsl.slRate || 0) + '%',
            rr: (data.tpsl.rr || 0).toString()
          };
        }
      }
    });

    this.agentService.getRecentTrades().subscribe((data: any) => {
      if (data && data.length) {
        this.operations = data.map((t: any, i: number) => ({
          id: '#' + (1000 + i),
          symbol: t.symbol,
          direction: t.direction,
          entry: t.entry,
          exit: t.exit_price,
          resultType: t.result,
          resultVal: (parseFloat(t.pnl_usd) > 0 ? '+' : '') + t.pnl_usd + ' USDT',
          strategy: t.source,
          group: t.nexus_group || 'N/A',
          conf: t.confluence || t.nexus_confidence || 0,
          date: t.date,
          reason: t.entry_reason || 'Sin detalles'
        }));
      }
    });

    this.agentService.getTopSymbols().subscribe((data: any) => {
      if (data && data.length) {
        this.topSymbols = data.map((s: any) => ({
          symbol: s.symbol,
          winRate: s.winRate + '%',
          pnl: (s.pnl > 0 ? '+' : '') + s.pnl,
          trades: s.trades
        }));
      }
    });
  }

  // --- UI Helpers ---

  get agentStatusText(): string {
    switch (this.systemState) {
      case 'STOPPED': return 'SERVICIOS DETENIDOS';
      case 'STARTING_SERVER': return 'CARGANDO SERVICIOS...';
      case 'SERVER_READY': return 'SERVICIOS EN LÍNEA';
      case 'AGENT_RUNNING': return 'AGENTE EN EJECUCIÓN';
      default: return 'DESCONOCIDO';
    }
  }

  get agentStatusColor(): string {
    switch (this.systemState) {
      case 'STOPPED': return '#ef4444'; // red
      case 'STARTING_SERVER': return '#f59e0b'; // yellow
      case 'SERVER_READY': return '#10b981'; // green
      case 'AGENT_RUNNING': return '#10b981'; // green
      default: return '#64748b'; // gray
    }
  }

  getServiceStatus(key: string): { text: string, class: string } {
    if (this.systemState === 'STOPPED' || this.systemState === 'STARTING_SERVER') {
      return { text: 'DESCONECTADO', class: 'text-danger' };
    }
    
    // Check real-time status if available
    if (this.exchangeStats) {
        // 1. Check WebSocket status
        const ws = this.exchangeStats.exchanges?.[key];
        if (ws?.connected) return { text: 'ACTIVO', class: 'text-success' };

        // 2. Check Circuit Breaker status (most reliable for REST fallbacks)
        const cb = this.exchangeStats.circuit_breakers?.[key];
        if (cb) {
            if (cb.state === 'OPEN' || cb.stat_418s > 0) {
              return { text: 'BANEADO (418)', class: 'text-danger' };
            }
            if (cb.state === 'HALF_OPEN') return { text: 'PROBANDO...', class: 'text-warning' };
            if (cb.is_available) return { text: 'STANDBY / OK', class: 'text-success' };
        }

        if (ws?.reconnects > 0) return { text: 'RECONECTANDO...', class: 'text-warning' };
    }

    // If backend is online but health telemetry is unavailable, do not show "initializing" forever.
    if (!this.exchangeStats) {
      if (key === 'nexus' || key === 'scar') return { text: 'ACTIVO', class: 'text-success' };
      return this.systemState === 'AGENT_RUNNING' || this.systemState === 'SERVER_READY'
        ? { text: 'ACTIVO', class: 'text-success' }
        : { text: 'CONECTANDO...', class: 'text-warning' };
    }

    // Default statuses for non-exchange items
    if (key === 'nexus' || key === 'scar') return { text: 'ACTIVO', class: 'text-success' };
    
    return { text: 'INICIALIZANDO...', class: 'text-warning' };
  }

  // --- Actions ---

  startServer() {
    if (this.systemState !== 'STOPPED') return;
    this.systemState = 'STARTING_SERVER';
    this.addLog('Conectando al hub de señales...', '#64748b');

    this.agentSignalrService.startConnection().then(() => {
      this.addLog('✅ Hub conectado. Iniciando MarketWS...', '#10b981');
      this.agentService.startServer().subscribe({
        next: () => {},
        error: (err) => {
          this.addLog('❌ ERROR al iniciar servidor: ' + (err.message || 'Error desconocido'), '#ef4444');
          this.systemState = 'STOPPED';
        }
      });
    }).catch(err => {
      this.addLog('❌ No se pudo conectar al hub: ' + err, '#ef4444');
      this.systemState = 'STOPPED';
    });
  }



  startAgent() {
    if (this.systemState !== 'SERVER_READY') return;
    this.addLog('Iniciando Agente en el servidor...', '#64748b');
    this.agentService.startAgent().subscribe({
      next: () => {},
      error: (err) => {
        this.addLog('❌ ERROR al iniciar agente: ' + (err.message || 'Error desconocido'), '#ef4444');
      }
    });
  }

  stopAgent() {
    if (this.systemState !== 'AGENT_RUNNING') return;
    this.agentService.stopAgent().subscribe();
  }

  clearLogs() {
    this.terminalLogs = [];
  }

  private addLog(text: string, color?: string) {
    this.terminalLogs.push({
      time: this.getCurrentTime(),
      text: text,
      color: color
    });
    // Keep terminal history large enough (like a real terminal)
    if (this.terminalLogs.length > 10000) {
      this.terminalLogs.shift();
    }
  }

  private getCurrentTime(): string {
    const now = new Date();
    return now.toTimeString().split(' ')[0]; // HH:MM:SS
  }

  private startUptime() {
    if (!this.startTimestamp) {
        this.startTimestamp = Date.now();
    }
    if (this.startTime === '-') {
        this.startTime = `Hoy ${this.getCurrentTime()}`;
    }

    if (this.uptimeInterval) clearInterval(this.uptimeInterval);
    
    this.uptimeInterval = setInterval(() => {
      const diff = Math.floor((Date.now() - this.startTimestamp) / 1000);
      const h = Math.floor(diff / 3600).toString().padStart(2, '0');
      const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
      const s = Math.floor(diff % 60).toString().padStart(2, '0');
      this.uptime = `${h}:${m}:${s}`;
    }, 1000);
  }

  private stopUptime() {
    if (this.uptimeInterval) {
      clearInterval(this.uptimeInterval);
    }
    this.uptime = '00:00:00';
    this.startTime = '-';
  }
}

