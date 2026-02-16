import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../core/auth.service';
import { map, take } from 'rxjs/operators';

export const adminGuard: CanActivateFn = (route, state) => {
    const authService = inject(AuthService);
    const router = inject(Router);

    return authService.isAdmin$.pipe(
        take(1),
        map(isAdmin => {
            if (isAdmin) {
                return true;
            }

            console.warn('🚫 [AdminGuard] Acceso denegado. No eres administrador.');
            router.navigate(['/profile']);
            return false;
        })
    );
};
