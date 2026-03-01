// alerts.types.ts
// Usamos string literals para emular los enums de la app o si ya están exportados desde los proxies, usaríamos esos.

export interface VergeAlert {
    id: string;
    type: string;  // 'Stage1' | 'Stage2' | 'Stage3' | 'Stage4' | 'Custom' | 'System'
    title: string;
    message: string;
    timestamp: Date;
    read: boolean;

    // Datos específicos de trading
    crypto?: string;
    price?: number;
    confidence?: number;
    direction?: number; // 0 = Long, 1 = Short, etc según tu enum
    stage?: number;
    targetZone?: { low: number; high: number };

    // UI
    severity: string; // 'info' | 'warning' | 'success' | 'danger'
    icon: string;
}
