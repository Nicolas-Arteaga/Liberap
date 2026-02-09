import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';

export const APP_ROUTES: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./login/login.component').then(c => c.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('../shared/layout/mobile-layout/mobile-layout.component')
      .then(c => c.MobileLayoutComponent),
    children: [
      {
        path: '',
        pathMatch: 'full',
        loadComponent: () => import('./home/home.component').then(c => c.HomeComponent),
      },
      {
        path: 'signals',
        loadComponent: () => import('./signals/signals.component').then(c => c.SignalsComponent),
      },
      {
        path: 'profile',
        loadComponent: () => import('./profile/profile.component').then(c => c.ProfileComponent),
      },
      {
        path: 'dashboard',
        loadComponent: () => import('./dashboard/dashboard.component').then(c => c.DashboardComponent),
      },
      {
        path: 'dashboard-advanced',
        loadComponent: () => import('./dashboard-advanced/dashboard-advanced.component')
          .then(c => c.DashboardAdvancedComponent),
      },
      {
        path: 'configure-strategy',
        loadComponent: () => import('./configure-strategy/configure-strategy.component')
          .then(c => c.ConfigureStrategyComponent),
      },
      {
        path: 'negotiate-debt',
        loadComponent: () => import('./negotiate-debt/negotiate-debt.component')
          .then(c => c.NegotiateDebtComponent),
      },
      {
        path: 'history',
        loadComponent: () => import('./history/history.component').then(c => c.HistoryComponent),
      },
      {
        path: 'execute-trade',
        loadComponent: () => import('./execute-trade/execute-trade.component')
          .then(c => c.ExecuteTradeComponent),
      },
      {
        path: 'alerts',
        loadComponent: () => import('./alerts/alerts.component').then(c => c.AlertsSystemComponent),
      },
      {
        path: 'backtesting',
        loadComponent: () => import('./backtesting/backtesting.component')
          .then(c => c.BacktestingComponent),
      },
      // Rutas de ABP modules integradas en el layout móvil
      {
        path: 'identity',
        loadChildren: () => import('@abp/ng.identity').then(c => c.createRoutes()),
      },
      {
        path: 'tenant-management',
        loadChildren: () => import('@abp/ng.tenant-management').then(c => c.createRoutes()),
      },
      {
        path: 'setting-management',
        loadChildren: () => import('@abp/ng.setting-management').then(c => c.createRoutes()),
      },
      {
        path: 'account/my-profile',
        loadChildren: () => import('@abp/ng.account').then(c => c.createRoutes()),
      },
    ]
  },
  // Rutas de cuenta públicas (sin layout móvil, con layout propio de ABP)
  {
    path: 'account',
    loadChildren: () => import('@abp/ng.account').then(c => c.createRoutes()),
    data: {
      skipAuthGuard: true, // Esto evita que el authGuard se aplique
    },
  },
  {
    path: '**',
    redirectTo: '/login'
  }
];