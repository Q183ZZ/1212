import hashlib
import json
import math
import threading
import time

import requests

from cache import RouteCache
from voice import VoiceEngine


class YaobaoService:
    def __init__(self, config):
        self.cfg = config
        net = config.get("network", {})
        self.api_base = net.get("api_base", "http://127.0.0.1:3000").rstrip("/")
        self.timeout = float(net.get("timeout_s", 8))
        self.retries = int(net.get("retries", 2))
        self.backoff = net.get("retry_backoff_s", [0.5, 1.0, 2.0])

        cache_cfg = config.get("cache", {})
        self.cache = RouteCache(
            cache_cfg.get("db", "data/yaobao.sqlite3"),
            int(cache_cfg.get("max_routes", 20))
        )
        self.voice = VoiceEngine(config.get("voice", {}))

        self.lock = threading.Lock()
        self.last_fix = None
        self.last_route = self.cache.latest()
        self.online = True
        self.navigation_state = "idle"
        self.status_message = "等待 GPS"

    def set_gps(self, fix):
        self.last_fix = fix
        self.status_message = (
            f"GPS {fix.latitude:.6f},{fix.longitude:.6f} "
            f"卫星{fix.satellites or '-'} HDOP {fix.hdop or '-'}"
        )

    def current_position(self):
        if not self.last_fix:
            return None
        return {
            "latitude": self.last_fix.latitude,
            "longitude": self.last_fix.longitude,
            "altitude": self.last_fix.altitude,
            "speed_mps": self.last_fix.speed_mps,
            "heading_deg": self.last_fix.heading_deg,
            "satellites": self.last_fix.satellites,
            "hdop": self.last_fix.hdop,
            "quality": self.last_fix.quality,
            "timestamp": self.last_fix.timestamp,
        }

    @staticmethod
    def _key(start, end, tags):
        raw = json.dumps(
            {"start": start, "end": end, "tags": sorted(tags or [])},
            ensure_ascii=False, sort_keys=True
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _request(self, method, path, payload=None):
        url = self.api_base + path
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.request(
                    method, url, json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                self.online = True
                return response.json()
            except Exception as exc:
                last_exc = exc
                self.online = False
                if attempt < self.retries:
                    delay = self.backoff[min(attempt, len(self.backoff) - 1)]
                    time.sleep(delay)
        raise last_exc

    def plan_route(self, start, end, tags):
        key = self._key(start, end, tags)
        try:
            # 保留原业务接口：路线规划仍交给原后端。
            data = self._request(
                "POST", "/api/map/route",
                {"startPoint": start, "endPoint": end, "tags": tags or []}
            )
            self.cache.put(key, data)
            self.last_route = data
            self.navigation_state = "planning"
            self.status_message = "路线规划完成"
            return {"data": data, "offline": False}
        except Exception:
            cached = self.cache.get(key) or self.last_route
            self.navigation_state = "offline" if cached else "idle"
            self.status_message = "网络不可用，已切换离线模式"
            self.voice.speak("当前网络不可用，已切换离线模式")
            if cached:
                return {"data": cached, "offline": True}
            return {"data": None, "offline": True, "error": "NO_ROUTE_CACHE"}

    def ai_intent(self, text):
        try:
            data = self._request("POST", "/api/ai/chat", {"message": text})
            return {"data": data, "offline": False}
        except Exception:
            self.online = False
            self.status_message = "AI 暂时离线"
            self.voice.speak("网络不可用，暂时无法进行 AI 意图识别")
            return {
                "data": None,
                "offline": True,
                "error": "AI_OFFLINE"
            }

    def poi_search(self, keyword, mode="keyword"):
        location = None
        if self.last_fix:
            location = f"{self.last_fix.longitude},{self.last_fix.latitude}"
        payload = {"keyword": keyword, "location": location or "", "mode": mode}
        try:
            data = self._request("POST", "/api/map/poi", payload)
            return {"data": data, "offline": False}
        except Exception:
            self.voice.speak("当前网络不可用，附近地点搜索暂不可用")
            return {"data": None, "offline": True, "error": "POI_OFFLINE"}

    def speak_navigation(self, text):
        return self.voice.speak(text)

    def status(self):
        return {
            "gps": self.current_position(),
            "online": self.online,
            "navigation_state": self.navigation_state,
            "message": self.status_message,
            "has_cached_route": bool(self.last_route),
            "route": self.last_route,
        }
