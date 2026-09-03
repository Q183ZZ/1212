import math
import time


def haversine(a, b):
    """a/b = (lat, lon), return meters."""
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(h)))


def point_segment_distance_m(point, a, b):
    """
    近似局部投影计算点到经纬度线段的距离。
    对车载导航的几十米偏航判定足够用，避免依赖浏览器 AMap.GeometryUtil。
    """
    lat0 = math.radians(point[0])
    scale_x = 111320.0 * max(0.01, math.cos(lat0))
    scale_y = 110540.0

    px, py = point[1] * scale_x, point[0] * scale_y
    ax, ay = a[1] * scale_x, a[0] * scale_y
    bx, by = b[1] * scale_x, b[0] * scale_y

    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def distance_to_route_m(point, path):
    if not path or len(path) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(path) - 1):
        best = min(best, point_segment_distance_m(point, path[i], path[i + 1]))
    return best


class NavigationEngine:
    """
    对齐原网页导航状态机：
    idle -> planning -> navigating -> offRoute -> rerouting -> arrived

    偏航规则保持原业务逻辑：
    - 80m 内：认为仍在路线
    - 超过 80m 且距离上次重算 >= 20s：请求重新规划
    - 到终点 50m 内：判定到达
    """

    def __init__(self, service):
        self.service = service
        self.state = "idle"
        self.route_path = []
        self.end = None
        self.last_reroute_at = 0
        self.last_position = None
        self.last_heading = None
        self.last_speed = 0.0

    @staticmethod
    def normalize_path(path):
        out = []
        for p in path or []:
            try:
                if isinstance(p, dict):
                    lng = float(p.get("lng", p.get("longitude")))
                    lat = float(p.get("lat", p.get("latitude")))
                else:
                    lng = float(p[0])
                    lat = float(p[1])
                out.append((lat, lng))
            except (TypeError, ValueError, KeyError, IndexError):
                continue
        return out

    def load_route(self, data):
        path = self.normalize_path(data.get("path") if isinstance(data, dict) else [])
        if len(path) < 2:
            raise ValueError("INVALID_ROUTE_GEOMETRY")
        self.route_path = path

        end = data.get("toLngLat") or data.get("endLngLat")
        if end and len(end) >= 2:
            self.end = (float(end[1]), float(end[0]))
        else:
            self.end = path[-1]

        self.state = "navigating"
        self.service.navigation_state = self.state

    def update(self, fix):
        if self.state not in ("navigating", "offRoute", "rerouting"):
            return None

        point = (fix.latitude, fix.longitude)
        self.last_position = point
        if fix.heading_deg is not None:
            self.last_heading = fix.heading_deg
        self.last_speed = fix.speed_mps

        if self.end and haversine(point, self.end) < 50:
            self.state = "arrived"
            self.service.navigation_state = "arrived"
            self.service.speak_navigation("已到达目的地")
            return {"event": "arrived", "distance_m": haversine(point, self.end)}

        distance = distance_to_route_m(point, self.route_path)
        now = time.time()

        if distance <= 80:
            if self.state == "offRoute":
                self.state = "navigating"
            self.service.navigation_state = self.state
            return {"event": "tracking", "distance_to_route_m": distance}

        if now - self.last_reroute_at < 20:
            self.state = "offRoute"
            self.service.navigation_state = "offRoute"
            return {"event": "off_route_waiting", "distance_to_route_m": distance}

        self.last_reroute_at = now
        self.state = "rerouting"
        self.service.navigation_state = "rerouting"

        return {
            "event": "reroute_required",
            "distance_to_route_m": distance,
            "start": f"{fix.longitude},{fix.latitude}",
        }
