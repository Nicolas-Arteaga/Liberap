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

  // Performance General (Mock)
  balance = '12,847.32';
  winRate = '68.7%';
  trades = 47;
  pnlTotal = '+547.32';
  
  // Strategy Analysis (Mock)
  scarStats = { winRate: '61.3%', pnl: '+287.45', trades: 31, promWin: '+2.34%', promLoss: '-1.45%' };
  nexusStats = { winRate: '63.8%', pnl: '+312.88', trades: 36, promWin: '+2.67%', promLoss: '-1.38%' };
  confluenceStats = { winRate: '72.4%', pnl: '+524.67', trades: 29, promWin: '+3.12%', promLoss: '-1.12%' };
  tpslStats = { effectiveness: '68.9%', trades: 47, tpRate: '73.4%', slRate: '26.6%', rr: '2.34' };

  // Top Performers (Mock)
  topSymbols = [
    { symbol: 'SOLUSDT', winRate: '75.6%', pnl: '+156.72', trades: 13 },
    { symbol: 'SUIUSDT', winRate: '72.2%', pnl: '+128.45', trades: 9 },
    { symbol: 'BTCUSDT', winRate: '68.3%', pnl: '+98.23', trades: 7 },
    { symbol: 'ETHUSDT', winRate: '66.7%', pnl: '+87.12', trades: 6 },
    { symbol: 'LINKUSDT', winRate: '64.3%', pnl: '+76.34', trades: 5 }
  ];

  // Recent Operations (Mock)
  operations = [
    { id: '#8934', symbol: 'SOLUSDT', direction: 'LONG', entry: '150.72', exit: '152.45', resultType: 'TP', resultVal: '+1.73%', strategy: 'CONFLUENCIA', group: 'NEXUS-15 (75%) + SCAR (68%)', conf: 75, date: '26/05 15:32:50' },
    { id: '#8933', symbol: 'SUIUSDT', direction: 'LONG', entry: '1.8721', exit: '1.9345', resultType: 'TP', resultVal: '+3.34%', strategy: 'NEXUS-15', group: 'Grupo Impulso Alcista', conf: 72, date: '26/05 15:18:23' },
    { id: '#8932', symbol: 'BTCUSDT', direction: 'SHORT', entry: '68,432.10', exit: '67,891.20', resultType: 'TP', resultVal: '+0.79%', strategy: 'SCAR', group: 'Grupo Mean Reversion', conf: 61, date: '26/05 15:05:11' },
    { id: '#8931', symbol: 'ETHUSDT', direction: 'LONG', entry: '3,245.50', exit: '3,198.20', resultType: 'SL', resultVal: '-1.46%', strategy: 'CONFLUENCIA', group: 'NEXUS-15 (62%) + SCAR (65%)', conf: 62, date: '26/05 14:45:33' },
    { id: '#8930', symbol: 'LINKUSDT', direction: 'LONG', entry: '15.872', exit: '16.234', resultType: 'TP', resultVal: '+2.28%', strategy: 'NEXUS-15', group: 'Grupo Breakout', conf: 71, date: '26/05 14:32:18' }
  ];

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
        } else if (state === 'STOPPED') {
          this.stopUptime();
        }
      })
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    this.stopUptime();
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

    // CRITICAL: esperar que SignalR esté conectado ANTES de lanzar el proceso
    // para no perder el primer log de Python
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

