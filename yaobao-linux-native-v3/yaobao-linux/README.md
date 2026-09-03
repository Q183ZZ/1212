# 遥望·耀宝 Linux 原生运行版

这个版本把原来的浏览器运行时拆成 Linux 常驻服务，不再依赖浏览器的 Web Speech API 或 Web Geolocation。

## 运行链路

GT-U7 GPS
→ `/dev/ttyUSB0` 串口
→ NMEA 解析器
→ 本地定位状态
→ 路线/导航业务层
→ 本地缓存 + 后端 API
→ 小屏显示 + 本地 TTS/STT + Bluetooth 音箱

网络正常：
- `/api/map/route`：路线规划
- `/api/map/poi`：POI 搜索
- `/api/ai/chat`：AI 意图解析

网络异常：
- 不让主循环因为请求异常退出
- 优先使用本地缓存的最近匹配路线
- 没有匹配路线时保留上一条路线
- TTS 播报“当前网络不可用，已切换离线模式”等本地提示
- GPS 仍然继续工作，因为 GPS 串口本身不需要互联网

## Bluetooth 音箱（V1.1）

耀宝现在按“实体导航 + AI语音 + Bluetooth 音箱”设计。Bluetooth 不需要手机 App，手机直接在系统 Bluetooth 设置中配对耀宝。

- 优先使用 Orange Pi 的板载 Bluetooth + Linux BlueZ。
- 如果最终选用的 Orange Pi Zero SKU 没有板载 Bluetooth，使用 USB Bluetooth 5.x 模块。
- Bluetooth 音频进入 Linux 音频层后送到独立 Class-D 双声道功放，再驱动左右两个 8Ω/2W 扬声器。
- 导航播报/AI TTS 时自动降低音乐音量，播报结束恢复。
- 网络断开时 Bluetooth 音箱仍可工作。
- 麦克风路径预留 AEC，避免播放音乐时把耀宝自己的声音重新识别成用户语音。

线路图：`hardware/bluetooth-speaker-wiring.svg`
详细说明：`docs/bluetooth-speaker-wiring.md`

## 默认硬件

GT-U7 常见串口：
- `/dev/ttyUSB0`
- `/dev/ttyACM0`

默认波特率：9600。

配置见 `config.json`。

## 安装

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv portaudio19-dev libsndfile1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
```

本地离线语音：

```bash
# STT：Vosk
pip install vosk sounddevice

# TTS：Piper（系统已有 piper 可直接使用）
sudo apt install -y piper
```

把 Vosk 中文模型放到 `models/vosk-zh/`，把 Piper 中文模型放到 `models/piper/`，具体模型文件名写入 `config.json`。

如果暂时没有语音模型，程序仍能启动，语音模块会自动降级为不可用，不影响 GPS/路线缓存。

## 启动

```bash
source .venv/bin/activate
python3 main.py
```

本地状态接口：

```text
GET  http://127.0.0.1:3900/status
POST http://127.0.0.1:3900/command
```

`POST /command` 示例：

```json
{"type":"plan","start":"当前位置","end":"石家庄站","tags":["红绿灯少"]}
```

## systemd 常驻进程

把项目复制到：

```text
/opt/yaobao
```

然后：

```bash
sudo cp yaobao.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable yaobao
sudo systemctl start yaobao
sudo systemctl status yaobao
```

## 设计原则

没有重写路线、AI 意图、标签这些业务规则。导航状态机也保留了原网页的核心阈值：偏离路线超过 80m 且 20 秒冷却结束才重新规划，到终点 50m 内判定到达。原网页中的 `/api/map/route`、`/api/map/poi`、`/api/ai/chat` 仍然是业务入口，只是调用者从浏览器 JavaScript 换成了 Linux 本地服务。

地图 JS 渲染层不再作为运行依赖。小屏只显示路线摘要、定位状态、网络状态和导航状态；真正的路线数据保存在本地缓存。
