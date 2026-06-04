import os
import time
from datetime import datetime

import pytz
import requests

# ---------- 中国区 Tesla API ----------
BASE_URL = "https://owner-api.vn.cloud.tesla.cn"
AUTH_URL = "https://auth.tesla.cn/oauth2/v3/token"
CLIENT_ID = "ownerapi"

REFRESH_TOKEN = os.environ["TESLA_REFRESH_TOKEN"]


# ---------- 1. 使用 refresh_token 获取 access_token ----------
def get_token():
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": REFRESH_TOKEN,
    }
    r = requests.post(
        AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"认证失败: {r.text}")
        return None
    data = r.json()
    # 特斯拉可能轮换 refresh_token；若返回新的，建议更新 GitHub Secret
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != REFRESH_TOKEN:
        print("提示: 收到新的 refresh_token，请更新 GitHub Secret TESLA_REFRESH_TOKEN")
    print("成功获取 access_token")
    return data["access_token"]


# ---------- 2. 获取车辆列表 ----------
def get_vehicles(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/api/1/vehicles", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"获取车辆列表失败: {r.text}")
        return []
    return r.json()["response"]


# ---------- 3. 获取车辆数据（唤醒并等待） ----------
def get_vehicle_data(token, vehicle_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/api/1/vehicles/{vehicle_id}/wake_up",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        print(f"唤醒请求: {r.status_code} {r.text}")

    for _ in range(20):
        r = requests.get(
            f"{BASE_URL}/api/1/vehicles/{vehicle_id}",
            headers=headers,
            timeout=30,
        )
        state = r.json()["response"]["state"]
        if state == "online":
            break
        time.sleep(2)
    else:
        print("车辆未在线")
        return None

    r = requests.get(
        f"{BASE_URL}/api/1/vehicles/{vehicle_id}/vehicle_data",
        headers=headers,
        timeout=60,
    )
    if r.status_code != 200:
        print(f"获取车辆数据失败: {r.text}")
        return None
    return r.json()["response"]


# ---------- 4. 获取最近行程（占位，需长期采样后自行实现） ----------
def get_recent_trips(token, vehicle_id):
    return []


# ---------- 5. 生成简单报告网页 ----------
def generate_html(vehicle_data, trips, charge_data):
    vehicle_state = vehicle_data.get("vehicle_state", {})
    charge_state = vehicle_data.get("charge_state", {})

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
<h2>📊 行程记录</h2>
<p>需长期定时采样后积累历史行程，当前为单次快照。</p>
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

    vehicle = vehicles[0]
    vehicle_id = vehicle["id"]
    print(f"车辆 VIN: {vehicle['vin']}, ID: {vehicle_id}")

    data = get_vehicle_data(token, vehicle_id)
    if not data:
        exit(1)

    trips = get_recent_trips(token, vehicle_id)
    generate_html(data, trips, data.get("charge_state", {}))
    print("报告已生成: index.html")
