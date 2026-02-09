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

  if (authService.isAuthenticated()) {
    return true;
  }

  // Redirigir a login
  return router.createUrlTree(['/login'], {
    queryParams: { returnUrl: router.url }
  });
};