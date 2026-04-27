import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonIcon } from '@ionic/angular/standalone';

@Component({
  selector: 'app-agent',
  standalone: true,
  imports: [CommonModule, IonIcon],
  templateUrl: './agent.component.html',
  styleUrls: ['./agent.component.scss']
})
export class AgentComponent implements OnInit {

  // Control Panel
  agentStatus = 'AGENTE EN EJECUCIÓN';
  uptime = '02:45:18';
  startTime = 'Hoy 15:32:41';
  
  services = [
    { name: 'API Binance', status: 'CONECTADO', statusClass: 'text-success' },
    { name: 'WebSocket Stream', status: 'CONECTADO', statusClass: 'text-success' },
    { name: 'Datos de Velas', status: 'SINCRONIZADO', statusClass: 'text-success' },
    { name: 'Motor de Predicción (NEXUS-15)', status: 'ACTIVO', statusClass: 'text-success' },
    { name: 'SCAR Signal Engine', status: 'ACTIVO', statusClass: 'text-success' },
    { name: 'Gestor de Riesgo', status: 'ACTIVO', statusClass: 'text-success' }
  ];

  // Terminal Logs
  terminalLogs = [
    { time: '15:32:41', text: '🚀 Agente Verge iniciado correctamente' },
    { time: '15:32:41', text: 'Conectando a Binance Futures API...' },
    { time: '15:32:42', text: 'WebSocket stream conectado' },
    { time: '15:32:42', text: 'Cargando datos de mercado...' },
    { time: '15:32:45', text: 'NEXUS-15 cargado (68,7% confianza promedio)' },
    { time: '15:32:45', text: 'SCAR Engine online' },
    { time: '15:32:45', text: 'Gestor de riesgo activado (TP/SL dinámico)' },
    { time: '15:32:46', text: 'Escaneando oportunidades...' },
    { time: '15:32:50', text: 'Señal detectada SOLUSDT LONG', highlight: true },
    { time: '15:32:50', text: 'Confluencia: NEXUS-15 (75%) + SCAR (68%)' },
    { time: '15:32:50', text: 'Entrada ejecutada en 150.72 USDT' },
    { time: '15:32:50', text: 'SL: 149.21 | TP: 153.85 | Riesgo: 1.2%' },
    { time: '15:32:52', text: 'Monitoreando posición...' }
  ];

  // Performance General
  balance = '12,847.32';
  winRate = '68.7%';
  trades = 47;
  pnlTotal = '+547.32';
  
  // Strategy Analysis
  scarStats = { winRate: '61.3%', pnl: '+287.45', trades: 31, promWin: '+2.34%', promLoss: '-1.45%' };
  nexusStats = { winRate: '63.8%', pnl: '+312.88', trades: 36, promWin: '+2.67%', promLoss: '-1.38%' };
  confluenceStats = { winRate: '72.4%', pnl: '+524.67', trades: 29, promWin: '+3.12%', promLoss: '-1.12%' };
  tpslStats = { effectiveness: '68.9%', trades: 47, tpRate: '73.4%', slRate: '26.6%', rr: '2.34' };

  // Top Performers
  topSymbols = [
    { symbol: 'SOLUSDT', winRate: '75.6%', pnl: '+156.72', trades: 13 },
    { symbol: 'SUIUSDT', winRate: '72.2%', pnl: '+128.45', trades: 9 },
    { symbol: 'BTCUSDT', winRate: '68.3%', pnl: '+98.23', trades: 7 },
    { symbol: 'ETHUSDT', winRate: '66.7%', pnl: '+87.12', trades: 6 },
    { symbol: 'LINKUSDT', winRate: '64.3%', pnl: '+76.34', trades: 5 }
  ];

  // Recent Operations
  operations = [
    { id: '#8934', symbol: 'SOLUSDT', direction: 'LONG', entry: '150.72', exit: '152.45', resultType: 'TP', resultVal: '+1.73%', strategy: 'CONFLUENCIA', group: 'NEXUS-15 (75%) + SCAR (68%)', conf: 75, date: '26/05 15:32:50' },
    { id: '#8933', symbol: 'SUIUSDT', direction: 'LONG', entry: '1.8721', exit: '1.9345', resultType: 'TP', resultVal: '+3.34%', strategy: 'NEXUS-15', group: 'Grupo Impulso Alcista', conf: 72, date: '26/05 15:18:23' },
    { id: '#8932', symbol: 'BTCUSDT', direction: 'SHORT', entry: '68,432.10', exit: '67,891.20', resultType: 'TP', resultVal: '+0.79%', strategy: 'SCAR', group: 'Grupo Mean Reversion', conf: 61, date: '26/05 15:05:11' },
    { id: '#8931', symbol: 'ETHUSDT', direction: 'LONG', entry: '3,245.50', exit: '3,198.20', resultType: 'SL', resultVal: '-1.46%', strategy: 'CONFLUENCIA', group: 'NEXUS-15 (62%) + SCAR (65%)', conf: 62, date: '26/05 14:45:33' },
    { id: '#8930', symbol: 'LINKUSDT', direction: 'LONG', entry: '15.872', exit: '16.234', resultType: 'TP', resultVal: '+2.28%', strategy: 'NEXUS-15', group: 'Grupo Breakout', conf: 71, date: '26/05 14:32:18' }
  ];

  constructor() { }

  ngOnInit(): void {
  }

}
