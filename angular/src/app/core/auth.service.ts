import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { tap, catchError, map } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../../environments/environment';
import { LoginRequest } from './models/login-request.model';

export const AUTH_TOKEN_KEY = 'verge_access_token';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = environment.apis?.default?.url || 'https://localhost:44396';
  private tokenKey = AUTH_TOKEN_KEY;
  private currentUserSubject = new BehaviorSubject<any>(null);

  public currentUser$ = this.currentUserSubject.asObservable();
  public isAdmin$ = this.currentUser$.pipe(
    map(user => {
      if (!user) return false;
      const roles = user.roleNames || user.roles || [];
      return roles.some((r: any) => {
        const roleName = typeof r === 'string' ? r : (r?.name || '');
        return roleName.toLowerCase() === 'admin';
      });
    })
  );

  private http = inject(HttpClient);
  private router = inject(Router);

  constructor() {
    this.loadInitialUser();
  }

  login(request: LoginRequest): Observable<any> {
    const url = `${this.apiUrl}/connect/token`;

    const body = new HttpParams()
      .set('grant_type', 'password')
      .set('username', request.userNameOrEmailAddress)
      .set('password', request.password)
      .set('client_id', 'Verge_App')
      .set('scope', 'offline_access Verge email profile roles');

    const headers = new HttpHeaders({
      'Content-Type': 'application/x-www-form-urlencoded'
    });

    console.log('📤 Enviando login OAuth2 a:', url);

    return this.http.post<any>(url, body.toString(), { headers }).pipe(
      tap({
        next: (response) => {
          console.log('✅ Login exitoso:', response);
          if (response.access_token) {
            this.storeToken(response.access_token);
            this.loadUserProfile();
          }
          if (response.refresh_token) {
            localStorage.setItem('refresh_token', response.refresh_token);
          }
        },
        error: (error) => {
          console.error('❌ Error en login:', error);
        }
      })
    );
  }

  logout(): void {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem('user_profile');
    localStorage.removeItem('refresh_token');
    this.currentUserSubject.next(null);
    this.router.navigate(['/login']);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  getToken(): string | null {
    const token = localStorage.getItem(this.tokenKey);
    console.log('🔍 Leyendo token de localStorage:', token ? 'EXISTE' : 'NO EXISTE');
    return token;
  }

  private storeToken(token: string): void {
    console.log('💾 Guardando token en localStorage');
    localStorage.setItem(this.tokenKey, token);
    console.log('📦 localStorage después de guardar:', {
      access_token: localStorage.getItem(this.tokenKey)
    });
  }

  private decodeToken(token: string): any {
    try {
      const payload = token.split('.')[1];
      const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(atob(base64).split('').map((c) => {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(jsonPayload);
    } catch (e) {
      console.error('❌ Error decodificando JWT:', e);
      return null;
    }
  }

  private getRolesFromToken(token: string): string[] {
    const decoded = this.decodeToken(token);
    if (!decoded) return [];

    // Diferentes proveedores usan diferentes nombres de claims para roles
    const roles = decoded.role ||
      decoded.roles ||
      decoded['http://schemas.microsoft.com/ws/2008/06/identity/claims/role'] ||
      [];

    return Array.isArray(roles) ? roles : [roles];
  }

  private loadInitialUser(): void {
    const token = this.getToken();
    if (token) {
      const savedProfile = localStorage.getItem('user_profile');
      if (savedProfile) {
        const profile = JSON.parse(savedProfile);
        const tokenRoles = this.getRolesFromToken(token);

        // Combinar roles del token con el perfil guardado
        const enrichedProfile = {
          ...profile,
          roleNames: Array.from(new Set([...(profile.roleNames || []), ...tokenRoles]))
        };

        this.currentUserSubject.next(enrichedProfile);
      }
      this.loadUserProfile();
    }
  }

  private loadUserProfile(): void {
    const url = `${this.apiUrl}/api/account/my-profile`;
    const token = this.getToken();

    if (!token) return;

    const tokenData = this.decodeToken(token);
    const tokenRoles = this.getRolesFromToken(token);
    console.log('🔑 [AuthService] JWT Decodificado:', tokenData);
    console.log('🛡️ [AuthService] Roles del Token:', tokenRoles);

    this.http.get(url).subscribe({
      next: (profile: any) => {
        const enrichedProfile = {
          ...profile,
          roleNames: Array.from(new Set([...(profile.roleNames || []), ...tokenRoles]))
        };

        console.log('👤 [AuthService] Perfil API Enriquecido:', enrichedProfile);
        this.currentUserSubject.next(enrichedProfile);
        localStorage.setItem('user_profile', JSON.stringify(enrichedProfile));
      },
      error: (err) => {
        if (err.status === 401) {
          console.warn('ℹ️ [AuthService] 401 detectado en Perfil API. Usando datos del Token como respaldo.');

          if (tokenData) {
            const partialProfile = {
              userName: tokenData.unique_name || tokenData.name || tokenData.sub || 'Admin(Offline)',
              email: tokenData.email || '',
              roleNames: tokenRoles
            };
            this.currentUserSubject.next(partialProfile);
          } else {
            this.currentUserSubject.next(null);
            localStorage.removeItem('user_profile');
          }
        } else {
          console.error('❌ [AuthService] Error cargando perfil:', err);
        }
      }
    });
  }
}
