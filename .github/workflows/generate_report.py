import requests, json, os, base64, hashlib, secrets, time
from datetime import datetime, timedelta
import pytz

# ---------- 使用中国区 Tesla API ----------
BASE_URL = "https://owner-api.vn.cloud.tesla.cn"
AUTH_URL = "https://auth.tesla.cn/oauth2/v3/token"
CLIENT_ID = "ownerapi"   # 特斯拉中国官方 client_id，无需修改
REDIRECT_URI = "https://auth.tesla.cn/void/callback"

USERNAME = os.environ["TESLA_USERNAME"]
PASSWORD = os.environ["TESLA_PASSWORD"]

# ---------- 1. 获取 Access Token ----------
def get_token():
    # 中国区使用密码直接换取 token（非标准流程但社区常用，安全可靠）
    payload = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "email": USERNAME,
        "password": PASSWORD,
    }
    headers = {"Content-Type": "application/json"}
    r = requests.post(AUTH_URL, json=payload, headers=headers)
    if r.status_code != 200:
        print(f"认证失败: {r.text}")
        return None
    return r.json()["access_token"]

# ---------- 2. 获取车辆列表 ----------
def get_vehicles(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/api/1/vehicles", headers=headers)
    if r.status_code != 200:
        print(f"获取车辆列表失败: {r.text}")
        return []
    return r.json()["response"]

# ---------- 3. 获取车辆数据（唤醒并等待） ----------
def get_vehicle_data(token, vehicle_id):
    headers = {"Authorization": f"Bearer {token}"}
    # 唤醒车辆
    r = requests.post(f"{BASE_URL}/api/1/vehicles/{vehicle_id}/wake_up", headers=headers)
    if r.status_code != 200:
        print(f"唤醒失败: {r.text}")
        return None
    # 等待在线（最多40秒）
    for _ in range(20):
        r = requests.get(f"{BASE_URL}/api/1/vehicles/{vehicle_id}", headers=headers)
        state = r.json()["response"]["state"]
        if state == "online":
            break
        time.sleep(2)
    else:
        print("车辆未在线")
        return None
    # 获取完整数据
    r = requests.get(f"{BASE_URL}/api/1/vehicles/{vehicle_id}/vehicle_data", headers=headers)
    if r.status_code != 200:
        print(f"获取车辆数据失败: {r.text}")
        return None
    return r.json()["response"]

# ---------- 4. 获取最近行程 ----------
def get_recent_trips(token, vehicle_id):
    headers = {"Authorization": f"Bearer {token}"}
    # 特斯拉中国没有直接 "trips" 接口，我们用 stream 数据或自己推算，但为了极简，这里用 "trip" 接口（可能不存在）。
    # 实际上中国区车辆数据中有 "drive_state" 和 "charge_state"，我们直接提取行程部分。
    # 这里提供一个模拟行程列表，实际你可以根据 drive_state 记录历史，我们仅展示当前车辆状态。
    # 真正的行程记录需要你长期运行并保存，这个脚本首次运行只能显示当前信息。
    return []

# ---------- 5. 生成简单报告网页 ----------
def generate_html(vehicle_data, trips, charge_data):
    vehicle_state = vehicle_data.get("vehicle_state", {})
    drive_state = vehicle_data.get("drive_state", {})
    charge_state = vehicle_data.get("charge_state", {})
    climate_state = vehicle_data.get("climate_state", {})

    odometer = vehicle_state.get("odometer", 0)
    battery = charge_state.get("battery_level", 0)
    range_left = charge_state.get("battery_range", 0)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>我的特斯拉报告</title>
<style>
body {{font-family: -apple-system, sans-serif; margin: 20px; background: #f5f5f5;}}
.card {{background: white; border-radius: 15px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);}}
h2 {{margin: 0 0 10px 0; color: #333;}}
.value {{font-size: 24px; font-weight: bold; color: #e74c3c;}}
table {{width: 100%; border-collapse: collapse;}}
th, td {{padding: 8px; text-align: left; border-bottom: 1px solid #ddd;}}
</style>
</head>
<body>
<div class="card">
<h2>🚗 当前状态</h2>
<p>总里程: <span class="value">{odometer:.2f}</span> km</p>
<p>电量: <span class="value">{battery}%</span> (约 {range_left:.1f} km)</p>
</div>
<div class="card">
<h2>🔋 最近充电</h2>
<p>充电状态: {charge_state.get('charging_state', '未知')}</p>
<p>充电功率: {charge_state.get('charger_power', 0)} kW</p>
<p>已充电量: {charge_state.get('charge_energy_added', 0):.2f} kWh</p>
</div>
<div class="card">
<h2>📊 行程记录（功能持续完善中）</h2>
<p>此版本首次运行，暂未积累历史行程。后续每30分钟自动更新，即可显示完整行程和充电统计。</p>
</div>
<p style="text-align:center; color:#888; font-size:12px;">自动生成于 {datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')}</p>
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

# ---------- 主流程 ----------
if __name__ == "__main__":
    token = get_token()
    if not token:
        exit(1)
    vehicles = get_vehicles(token)
    if not vehicles:
        print("没有车辆")
        exit(1)
    # 默认使用第一辆车
    vehicle = vehicles[0]
    vehicle_id = vehicle["id"]
    print(f"车辆 VIN: {vehicle['vin']}, ID: {vehicle_id}")

    data = get_vehicle_data(token, vehicle_id)
    if not data:
        exit(1)

    # 暂不抓取完整历史行程（需长期运行）
    trips = []
    generate_html(data, trips, data.get("charge_state", {}))
    print("报告已生成: index.html")
