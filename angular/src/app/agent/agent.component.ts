import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';
import { AgentService } from '../proxy/agent/agent.service';
import { AgentSignalrService, AgentLog } from './agent-signalr.service';
import { Subscription } from 'rxjs';

export type SystemState = 'STOPPED' | 'STARTING_SERVER' | 'SERVER_READY' | 'AGENT_RUNNING';

@Component({
  selector: 'app-agent',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './agent.component.html',
  styleUrls: ['./agent.component.scss']
})
export class AgentComponent implements OnInit {

  // State Machine
  systemState: SystemState = 'STOPPED';

  // Control Panel
  uptime = '00:00:00';
  startTime = '-';
  
  services = [
    { name: 'API Binance', key: 'binance' },
    { name: 'WebSocket Stream', key: 'ws' },
    { name: 'Datos de Velas', key: 'klines' },
    { name: 'Motor de Predicción (NEXUS-15)', key: 'nexus' },
    { name: 'SCAR Signal Engine', key: 'scar' },
    { name: 'Gestor de Riesgo', key: 'risk' }
  ];

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

  private agentService = inject(AgentService);
  private agentSignalrService = inject(AgentSignalrService);
  private subscriptions = new Subscription();

  constructor() { }

  ngOnInit(): void {
    this.addLog('Sistema inicializado. Presioná INICIAR MARKET WS para comenzar.', '#64748b');

    this.subscriptions.add(
      this.agentSignalrService.logs$.subscribe((log: AgentLog) => {
        this.addLog(log.message, log.color);
      })
    );

    this.subscriptions.add(
      this.agentSignalrService.state$.subscribe((state: any) => {
        this.systemState = state as SystemState;
        if (state === 'SERVER_READY' && !this.uptimeInterval) {
          this.startUptime();
          this.startDataRefresh();
        } else if (state === 'STOPPED') {
          this.stopUptime();
          this.stopDataRefresh();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    this.stopUptime();
    this.stopDataRefresh();
  }

  // --- Data Fetching ---

  private startDataRefresh() {
    this.refreshData();
    this.refreshInterval = setInterval(() => this.refreshData(), 10000);
  }

  private stopDataRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  refreshData() {
    this.agentService.getAuditSummary().subscribe(data => {
      if (data) {
        this.balance = data.balance?.toLocaleString('en-US') || '0.00';
        this.winRate = (data.winRate || 0) + '%';
        this.trades = data.trades || 0;
        this.pnlTotal = (data.pnlTotal > 0 ? '+' : '') + (data.pnlTotal || 0).toLocaleString('en-US');
      }
    });

    this.agentService.getStrategyStats().subscribe(data => {
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

    this.agentService.getRecentTrades().subscribe(data => {
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

    this.agentService.getTopSymbols().subscribe(data => {
      if (data) {
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
    
    // In SERVER_READY or AGENT_RUNNING, all services are ready
    if (key === 'binance' || key === 'ws') return { text: 'CONECTADO', class: 'text-success' };
    if (key === 'klines') return { text: 'SINCRONIZADO', class: 'text-success' };
    return { text: 'ACTIVO', class: 'text-success' };
  }

  // --- Actions ---

  startServer() {
    if (this.systemState !== 'STOPPED') return;
    this.systemState = 'STARTING_SERVER';
    this.terminalLogs = [];
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

  stopServer() {
    this.agentService.stopServer().subscribe();
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
    // Optional: Keep terminal array size manageable
    if (this.terminalLogs.length > 50) {
      this.terminalLogs.shift();
    }
  }

  private getCurrentTime(): string {
    const now = new Date();
    return now.toTimeString().split(' ')[0]; // HH:MM:SS
  }

  private startUptime() {
    this.startTime = `Hoy ${this.getCurrentTime()}`;
    this.startTimestamp = Date.now();
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

