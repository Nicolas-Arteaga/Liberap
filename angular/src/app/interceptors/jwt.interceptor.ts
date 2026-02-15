import { inject, Injectable } from '@angular/core';
import {
    HttpRequest,
    HttpHandler,
    HttpEvent,
    HttpInterceptor,
    HttpErrorResponse
} from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Router } from '@angular/router';
import { AUTH_TOKEN_KEY } from '../core/auth.service';

@Injectable()
export class JwtInterceptor implements HttpInterceptor {
    private router = inject(Router);

    intercept(request: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
        // Acceso directo a localStorage para evitar dependencia circular con AuthService
        const token = localStorage.getItem(AUTH_TOKEN_KEY);

        let clonedRequest = request;

        // Solo añadir token si existe y NO es una request de autenticación
        if (token && !this.isAuthRequest(request)) {
            clonedRequest = request.clone({
                setHeaders: {
                    Authorization: `Bearer ${token}`
                }
            });
        }

        return next.handle(clonedRequest).pipe(
            catchError((error: HttpErrorResponse) => {
                if (error.status === 401) {
                    const isProfileRequest = request.url.includes('/api/account/my-profile');

                    if (!isProfileRequest) {
                        console.warn('🔴 [JwtInterceptor] 401 detectado. Cerrando sesión.');

                        // Limpieza manual de storage (lo que haría logout)
                        localStorage.removeItem(AUTH_TOKEN_KEY);
                        localStorage.removeItem('user_profile');
                        localStorage.removeItem('refresh_token');

                        this.router.navigate(['/login'], {
                            queryParams: { sessionExpired: true }
                        });
                    } else {
                        console.log('ℹ️ [JwtInterceptor] 401 en perfil. Delegando manejo al AuthService.');
                    }
                }
                return throwError(() => error);
            })
        );
    }

    private isAuthRequest(request: HttpRequest<any>): boolean {
        const url = request.url.toLowerCase();
        return url.includes('/api/account/login') ||
            url.includes('/connect/token') ||
            url.includes('/api/tokenauth/authenticate');
    }
}