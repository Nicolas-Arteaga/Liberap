import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { adminGuard } from './guards/admin.guard';

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
      {
        path: 'admin/users/create',
        canActivate: [adminGuard],
        loadComponent: () => import('./identity/create-user/create-user.component').then(c => c.CreateUserComponent),
      },
      // Rutas de ABP modules integradas en el layout móvil
      {
        path: 'identity',
        loadChildren: () => import('@abp/ng.identity').then(c => c.createRoutes()),
      },
      {
        path: 'setting-management',
        loadChildren: () => import('@abp/ng.setting-management').then(c => c.createRoutes()),
      },
    ]
  },
  // Rutas de cuenta (login, perfil, etc.)
  {
    path: 'account',
    loadChildren: () => import('@abp/ng.account').then(c => c.createRoutes()),
  },
  {
    path: '**',
    redirectTo: '/login'
  }
];