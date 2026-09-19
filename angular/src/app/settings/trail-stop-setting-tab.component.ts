import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToasterService } from '@abp/ng.theme.shared';
import { VergeGlobalSettingsService } from '../proxy/settings/verge-global-settings.service';

/**
 * ROUND 43 -- tab custom dentro de la pantalla estándar de Configuración
 * de Verge (Administración → Configuración), registrado vía
 * SettingTabsService. Único propósito: prender/apagar el interruptor
 * maestro global de Trail-1 (Verge.TrailStop.Enabled) sin tocar
 * appsettings.json ni reiniciar el backend.
 *
 * Trail-1 es una mejora de gestión de salida (overlay opcional), no una
 * estrategia — este switch queda en false salvo decisión explícita del
 * usuario, y aunque esté en true no hace nada si el StrategyProfile en
 * cuestión no tiene además su propio UseTrailStop activado.
 */
@Component({
  selector: 'app-trail-stop-setting-tab',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="py-2">
      <p class="text-muted mb-3">
        Interruptor maestro global de <strong>Trail-1</strong> (gestión de salida con SL
        dinámico). En <em>false</em>, ningún perfil recibe Trail-1 sin importar su propio
        toggle "Trailing stop (Trail-1)" en el editor de estrategias — defensa en
        profundidad. En <em>true</em>, aplica solo a los perfiles que además tengan ese
        toggle activado.
      </p>

      @if (loading) {
        <p>Cargando...</p>
      } @else {
        <div
          class="toggle-card"
          [class.on]="enabled"
          (click)="toggle()"
          style="display:inline-flex;align-items:center;gap:.5rem;border:1px solid rgb(0 196 125 / 40%);border-radius:8px;padding:.5rem 1rem;cursor:pointer;"
          [style.background]="enabled ? 'rgb(0 196 125 / 12%)' : ''"
        >
          <div class="toggle-dot"></div>
          <span>{{ enabled ? 'Trail-1 global: ACTIVADO' : 'Trail-1 global: DESACTIVADO' }}</span>
        </div>
      }
    </div>
  `,
})
export class TrailStopSettingTabComponent implements OnInit {
  private readonly service = inject(VergeGlobalSettingsService);
  private readonly toaster = inject(ToasterService);

  loading = true;
  enabled = false;

  ngOnInit(): void {
    this.service.getTrailStopSetting().subscribe({
      next: (dto) => {
        this.enabled = dto.enabled;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  toggle(): void {
    const next = !this.enabled;
    this.service.setTrailStopSetting({ enabled: next }).subscribe({
      next: (dto) => {
        this.enabled = dto.enabled;
        this.toaster.success(
          dto.enabled
            ? 'Trail-1 global activado.'
            : 'Trail-1 global desactivado.',
        );
      },
      error: () => {
        this.toaster.error('No se pudo actualizar el interruptor de Trail-1.');
      },
    });
  }
}
