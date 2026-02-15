import { inject } from '@angular/core';
import { CanActivateFn, Router, ActivatedRouteSnapshot } from '@angular/router';
import { AuthService } from '../core/auth.service';

export const authGuard: CanActivateFn = (route: ActivatedRouteSnapshot) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  // Verificar si la ruta tiene skipAuthGuard (para rutas públicas como /account/register)
  if (route.data?.['skipAuthGuard']) {
    return true;
  }

  const isAuth = authService.isAuthenticated();
  console.log('🛡️ AuthGuard - isAuthenticated:', isAuth);

  if (isAuth) {
    return true;
  }

  // Redirigir a login
  return router.createUrlTree(['/login'], {
    queryParams: { returnUrl: router.url }
  });
};