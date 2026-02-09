export interface LoginRequest {
    userNameOrEmailAddress: string;
    password: string;
    rememberMe?: boolean;
    twoFactorRememberClientToken?: string | null;
    twoFactorCode?: string | null;
    twoFactorProvider?: string | null;
}
