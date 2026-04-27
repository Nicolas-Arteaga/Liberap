import time
import logging
import requests
import config

logger = logging.getLogger("AuthManager")

class AuthManager:
    """
    Manages the ABP OpenIddict OAuth 2.0 authentication for the VERGE Agent.
    Fetches and refreshes the JWT token automatically.
    """
    def __init__(self):
        self.access_token = None
        self.expires_at = 0

    def get_token(self) -> str:
        """
        Returns a valid JWT token. If the current token is expired or missing,
        it requests a new one from the ABP backend.
        """
        # Buffer of 60 seconds to ensure token doesn't expire exactly when used
        if self.access_token and time.time() < (self.expires_at - 60):
            return self.access_token

        logger.info("[Auth] Fetching new JWT token from ABP Backend...")
        
        url = f"{config.ABP_BACKEND_URL}/connect/token"
        
        payload = {
            "grant_type": "password",
            "username": config.AGENT_USERNAME,
            "password": config.AGENT_PASSWORD,
            "client_id": config.CLIENT_ID,
            # Scope 'Verge' is the custom scope for the API.
            # 'openid' is standard for identifying the user.
            "scope": "Verge openid email profile roles offline_access"
        }

        if config.CLIENT_SECRET:
            payload["client_secret"] = config.CLIENT_SECRET

        # Intento de reconexión / Reintentos (3 intentos)
        for attempt in range(3):
            try:
                # verify=False because localhost dev certs are self-signed
                response = requests.post(url, data=payload, verify=False, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self.expires_at = time.time() + expires_in
                    logger.info("[Auth] JWT token successfully obtained. Expires in %ds", expires_in)
                    return self.access_token
                else:
                    logger.error("[Auth] Failed to obtain JWT token (Attempt %d/3): %s - %s", attempt + 1, response.status_code, response.text)
                    
            except requests.exceptions.RequestException as e:
                logger.warning("[Auth] Connection error (Attempt %d/3): %s", attempt + 1, e)
            
            if attempt < 2:
                time.sleep(5) # Esperar 5 seg antes de reintentar
                
        return None

    def get_auth_headers(self) -> dict:
        """
        Returns the authorization headers needed for ABP API calls.
        """
        token = self.get_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        return {}
