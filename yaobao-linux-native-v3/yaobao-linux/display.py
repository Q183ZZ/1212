import time


class SmallScreen:
    """
    轻量 Linux 小屏显示层。
    pygame 存在时显示原生窗口/全屏；没有 pygame 时退化为日志输出。
    业务服务完全不依赖这个模块。
    """

    def __init__(self, config, service):
        self.cfg = config or {}
        self.service = service
        self.enabled = bool(self.cfg.get("enabled", True))
        self.screen = None
        self.font = None

    def start(self):
        if not self.enabled:
            return
        try:
            import pygame
            pygame.init()
            flags = pygame.FULLSCREEN if self.cfg.get("fullscreen", True) else 0
            self.screen = pygame.display.set_mode(
                (self.cfg.get("width", 800), self.cfg.get("height", 480)),
                flags
            )
            pygame.display.set_caption("遥望·耀宝")
            self.font = pygame.font.SysFont(None, 30)
        except Exception:
            self.screen = None

    def loop(self, stop_event):
        if not self.enabled:
            while not stop_event.is_set():
                time.sleep(1)
            return

        if not self.screen:
            while not stop_event.is_set():
                print(self.service.status(), flush=True)
                time.sleep(2)
            return

        import pygame
        clock = pygame.time.Clock()
        while not stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_event.set()

            self.screen.fill((245, 245, 247))
            status = self.service.status()
            gps = status.get("gps")
            lines = [
                "遥望 · 耀宝",
                "在线" if status["online"] else "离线模式",
                status["navigation_state"],
                status["message"],
            ]
            if gps:
                lines += [
                    f"LAT {gps['latitude']:.6f}",
                    f"LON {gps['longitude']:.6f}",
                    f"SPD {gps['speed_mps']:.1f} m/s",
                ]
            if status["has_cached_route"]:
                lines.append("已缓存最近路线")

            y = 30
            for text in lines:
                surface = self.font.render(text, True, (25, 25, 25))
                self.screen.blit(surface, (30, y))
                y += 45

            pygame.display.flip()
            clock.tick(int(self.cfg.get("fps", 10)))
