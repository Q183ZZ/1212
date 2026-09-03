import os
import subprocess
import tempfile
import threading


class VoiceEngine:
    """
    Linux 语音适配层。
    默认：
      STT = Vosk（离线）
      TTS = Piper（离线）
    没有模型/二进制时不让主程序崩溃。
    """

    def __init__(self, config):
        self.cfg = config or {}
        self.stt_enabled = bool(self.cfg.get("stt", {}).get("enabled", True))
        self.tts_enabled = bool(self.cfg.get("tts", {}).get("enabled", True))
        self._lock = threading.Lock()

    def speak(self, text):
        if not text or not self.tts_enabled:
            return False
        cfg = self.cfg.get("tts", {})
        engine = cfg.get("engine", "piper")
        if engine != "piper":
            return False

        binary = cfg.get("binary", "piper")
        model = cfg.get("model", "")
        if not model or not os.path.exists(model):
            return False

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav = f.name
            subprocess.run(
                [binary, "--model", model, "--output_file", wav],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=True,
            )
            # 优先 paplay，若系统没有则尝试 aplay。
            for player in ("paplay", "aplay"):
                if subprocess.call(
                    ["which", player],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                ) == 0:
                    subprocess.Popen([player, wav],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    return True
        except Exception:
            return False
        finally:
            try:
                os.unlink(wav)
            except Exception:
                pass
        return False

    def listen_once(self, seconds=10):
        if not self.stt_enabled:
            return ""
        cfg = self.cfg.get("stt", {})
        if cfg.get("engine", "vosk") != "vosk":
            return ""

        model_path = cfg.get("model", "")
        if not os.path.isdir(model_path):
            return ""

        try:
            import json
            import queue
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer

            model = Model(model_path)
            recognizer = KaldiRecognizer(model, 16000)
            q = queue.Queue()

            def callback(indata, frames, time_info, status):
                q.put(bytes(indata))

            with sd.RawInputStream(
                samplerate=16000,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=callback
            ):
                end = __import__("time").time() + seconds
                while __import__("time").time() < end:
                    try:
                        data = q.get(timeout=1)
                    except queue.Empty:
                        continue
                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = (result.get("text") or "").strip()
                        if text:
                            return text
                result = json.loads(recognizer.FinalResult())
                return (result.get("text") or "").strip()
        except Exception:
            return ""
