import json
import os
import threading
from flask import Flask, jsonify, request

from gps import GTU7Reader
from service import YaobaoService
from display import SmallScreen
from navigation import NavigationEngine


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


cfg = load_config()
service = YaobaoService(cfg)
navigation = NavigationEngine(service)
stop_event = threading.Event()

app = Flask(__name__)


@app.get("/status")
def status():
    return jsonify(service.status())


@app.post("/command")
def command():
    body = request.get_json(silent=True) or {}
    typ = body.get("type")

    if typ == "plan":
        start = body.get("start") or (
            f"{service.last_fix.longitude},{service.last_fix.latitude}"
            if service.last_fix else ""
        )
        end = (body.get("end") or "").strip()
        tags = body.get("tags") or ["红绿灯少"]
        if not end:
            return jsonify({"success": False, "error": "MISSING_DESTINATION"}), 400
        result = service.plan_route(start, end, tags)
        if result.get("data"):
            try:
                navigation.load_route(result["data"])
            except Exception:
                pass
        return jsonify({"success": True, **result})

    if typ == "ai":
        text = (body.get("text") or "").strip()
        if not text:
            return jsonify({"success": False, "error": "EMPTY_TEXT"}), 400
        result = service.ai_intent(text)
        return jsonify({"success": True, **result})

    if typ == "speak":
        ok = service.speak_navigation(body.get("text") or "")
        return jsonify({"success": ok})

    return jsonify({"success": False, "error": "UNKNOWN_COMMAND"}), 400


def gps_fix(fix):
    service.set_gps(fix)
    event = navigation.update(fix)
    if event and event.get("event") == "reroute_required":
        end = navigation.end
        if end:
            result = service.plan_route(
                event["start"],
                f"{end[1]},{end[0]}",
                service.last_route.get("tags", ["红绿灯少"]) if isinstance(service.last_route, dict) else ["红绿灯少"]
            )
            if result.get("data"):
                try:
                    navigation.load_route(result["data"])
                except Exception:
                    navigation.state = "offRoute"
                    service.navigation_state = "offRoute"


def gps_error(exc):
    service.status_message = f"GPS 串口异常: {exc}"


def run():
    os.makedirs("data", exist_ok=True)

    gps_cfg = cfg.get("gps", {})
    reader = GTU7Reader(
        gps_cfg.get("device", "/dev/ttyUSB0"),
        int(gps_cfg.get("baudrate", 9600)),
        on_fix=gps_fix,
        on_error=gps_error
    )
    reader.start()

    display = SmallScreen(cfg.get("display", {}), service)
    display.start()

    ui_thread = threading.Thread(target=display.loop, args=(stop_event,), daemon=True)
    ui_thread.start()

    try:
        # 本地控制接口，仅监听回环地址，不暴露到局域网。
        app.run(host="127.0.0.1", port=3900, threaded=True)
    finally:
        stop_event.set()
        reader.stop()


if __name__ == "__main__":
    run()
