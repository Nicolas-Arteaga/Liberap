import { Routes } from '@angular/router';
import { eLayoutType } from '@abp/ng.core';

export const APP_ROUTES: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./login/login.component').then(c => c.LoginComponent),
    data: {
      layout: eLayoutType.empty,  
    },
  },
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./home/home.component').then(c => c.HomeComponent),
  },
  {
    path: 'debts',
    loadComponent: () => import('./debts/debts.component').then(c => c.DebtsComponent),
  },
  {
    path: 'profile',
    loadComponent: () => import('./profile/profile.component').then(c => c.ProfileComponent),
  },
  {
    path: 'debt-detail',
    loadComponent: () => import('./debt-detail/debt-detail.component').then(c => c.DebtDetailComponent),
  }, 
  {
    path: 'register-payment',
    loadComponent: () => import('./register-payment/register-payment.component').then(c => c.RegisterPaymentComponent),
  },
  {
    path: 'add-debt',
    loadComponent: () => import('./add-debt/add-debt.component').then(c => c.AddDebtComponent),
  },
  {
    path: 'negotiate-debt',
    loadComponent: () => import('./negotiate-debt/negotiate-debt.component').then(c => c.NegotiateDebtComponent),
  },
  {
    path: 'history',
    loadComponent: () => import('./history/history.component').then(c => c.HistoryComponent),
  },
  {
    path: 'account',
    loadChildren: () => import('@abp/ng.account').then(c => c.createRoutes()),
  },
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
];
