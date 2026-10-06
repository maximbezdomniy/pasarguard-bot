# pasarguard_api.py
import time
import httpx
from typing import Optional, Dict, Any
import config

class PasarGuardAPI:
    def __init__(self):
        self.base_url = config.PANEL_URL.rstrip('/')
        self.username = config.API_USERNAME
        self.password = config.API_PASSWORD
        self._token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_token(self) -> str:
        """Получает или обновляет JWT-токен доступа"""
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        url = f"{self.base_url}/api/admin/token"
        data = {
            "username": self.username,
            "password": self.password
        }
        
        # verify=False защищает от ошибок SSL, если поднят HTTPS
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(url, data=data)
            if response.status_code != 200:
                raise Exception(f"Ошибка авторизации в PasarGuard: {response.text}")
            
            result = response.json()
            self._token = result["access_token"]
            self._token_expires = time.time() + 3600 
            return self._token

    async def _get_headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def create_user(self, username: str, days: int, data_limit_gb: int) -> Optional[Dict[str, Any]]:
        """Создает нового пользователя в Xray/PasarGuard с привязкой к группе"""
        url = f"{self.base_url}/api/user"
        
        expire_timestamp = int(time.time()) + (days * 86400)
        data_limit_bytes = data_limit_gb * 1024 * 1024 * 1024

        payload = {
            "username": username,
            "proxies": {"vless": {}},
            "expire": expire_timestamp,
            "data_limit": data_limit_bytes,
            "group_ids": config.USER_GROUP_IDS  # Передаем ID группы
        }

        async with httpx.AsyncClient(verify=False) as client:
            headers = await self._get_headers()
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code in (200, 201):
                return response.json()
            else:
                print(f"Ошибка создания пользователя {username}: {response.text}")
                return None

    async def extend_user(self, username: str, days: int) -> bool:
        """Продлевает подписку пользователя на N дней и сбрасывает счетчик трафика"""
        url_modify = f"{self.base_url}/api/user/{username}"
        url_reset = f"{self.base_url}/api/user/{username}/reset"

        async with httpx.AsyncClient(verify=False) as client:
            headers = await self._get_headers()
            
            get_response = await client.get(url_modify, headers=headers)
            if get_response.status_code != 200:
                return False
            
            current_user = get_response.json()
            raw_expire = current_user.get("expire")
            
            # БЕЗОПАСНЫЙ КАСТ СТРОКИ ИЗ API В INTEGER
            try:
                current_expire = int(raw_expire) if raw_expire else int(time.time())
            except (ValueError, TypeError):
                current_expire = int(time.time())
            
            base_time = max(current_expire, int(time.time()))
            new_expire = base_time + (days * 86400)

            payload = {"expire": new_expire}
            modify_response = await client.put(url_modify, json=payload, headers=headers)
            await client.post(url_reset, headers=headers)

            return modify_response.status_code == 200