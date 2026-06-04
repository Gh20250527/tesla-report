import os
import time
from datetime import datetime

import pytz
import requests

# 中国区：车辆列表等已迁移到 Fleet API；部分接口仍可用 Owner API
OWNER_API = "https://owner-api.vn.cloud.tesla.cn"
FLEET_API = "https://fleet-api.prd.cn.vn.cloud.tesla.cn"
AUTH_URL = "https://auth.tesla.cn/oauth2/v3/token"
CLIENT_ID = "ownerapi"

REFRESH_TOKEN = os.environ.get("TESLA_REFRESH_TOKEN", "").strip()
if not REFRESH_TOKEN:
    print(
        "错误: 未设置环境变量 TESLA_REFRESH_TOKEN。\n"
        "请在 GitHub 仓库 Settings → Secrets and variables → Actions 中\n"
        "新建 Secret，名称必须为 TESLA_REFRESH_TOKEN。"
    )
    raise SystemExit(1)


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != REFRESH_TOKEN:
        print("提示: 收到新的 refresh_token，请更新 GitHub Secret TESLA_REFRESH_TOKEN")
    print("成功获取 access_token")
    return data["access_token"]


def _parse_products(data: dict) -> list[dict]:
    """从 /products 中筛出车辆（含 vin）。"""
    items = data.get("response") or []
    vehicles = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("vin"):
            vehicles.append(
                {
                    "id": item.get("id") or item.get("id_s"),
                    "id_s": item.get("id_s"),
                    "vin": item.get("vin"),
                    "display_name": item.get("display_name", "Tesla"),
                    "vehicle_id": item.get("vehicle_id"),
                    "state": item.get("state"),
                    "_api": "owner",
                }
            )
    return vehicles


def get_vehicles(token: str) -> list[dict]:
    headers = auth_headers(token)

    # 1) Fleet API（官方推荐）
    r = requests.get(f"{FLEET_API}/api/1/vehicles", headers=headers, timeout=30)
    if r.status_code == 200:
        vehicles = r.json().get("response") or []
        for v in vehicles:
            v["_api"] = "fleet"
        if vehicles:
            print(f"通过 Fleet API 获取到 {len(vehicles)} 辆车")
            return vehicles
    print(f"Fleet API /vehicles: {r.status_code} {r.text[:300]}")

    # 2) Owner API /products（社区常用替代 /vehicles）
    r = requests.get(
        f"{OWNER_API}/api/1/products",
        headers=headers,
        params={"orders": "true"},
        timeout=30,
    )
    if r.status_code == 200:
        vehicles = _parse_products(r.json())
        if vehicles:
            print(f"通过 Owner API /products 获取到 {len(vehicles)} 辆车")
            return vehicles
    print(f"Owner API /products: {r.status_code} {r.text[:300]}")

    return []


def get_vehicle_data(token: str, vehicle: dict):
    headers = auth_headers(token)
    vin = vehicle.get("vin")
    vid = vehicle.get("id") or vehicle.get("id_s")
    use_fleet = vehicle.get("_api") == "fleet" and vin

    bases = []
    if use_fleet:
        bases.append(("fleet", FLEET_API, vin))
    if vid:
        bases.append(("owner", OWNER_API, str(vid)))
    if vin and not use_fleet:
        bases.append(("fleet", FLEET_API, vin))

    for api_name, base, resource_id in bases:
        print(f"尝试 {api_name} API 获取车辆数据 (id/vin={resource_id})…")
        requests.post(
            f"{base}/api/1/vehicles/{resource_id}/wake_up",
            headers=headers,
            timeout=30,
        )

        for _ in range(20):
            r = requests.get(
                f"{base}/api/1/vehicles/{resource_id}",
                headers=headers,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"  状态查询失败: {r.status_code} {r.text[:200]}")
                break
            state = r.json().get("response", {}).get("state")
            print(f"  车辆状态: {state}")
            if state == "online":
                break
            time.sleep(2)
        else:
            print("  车辆长时间未在线，仍尝试拉取 vehicle_data…")

        r = requests.get(
            f"{base}/api/1/vehicles/{resource_id}/vehicle_data",
            headers=headers,
            timeout=90,
        )
        if r.status_code == 200:
            print(f"  已从 {api_name} API 获取 vehicle_data")
            return r.json().get("response")
        print(f"  vehicle_data 失败: {r.status_code} {r.text[:300]}")

    return None


def get_recent_trips(token, vehicle):
    return []


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


if __name__ == "__main__":
    token = get_token()
    if not token:
        exit(1)

    vehicles = get_vehicles(token)
    if not vehicles:
        print("没有车辆。若持续失败，可能需使用 Fleet API 专用 token（developer.tesla.cn 注册应用）。")
        exit(1)

    vehicle = vehicles[0]
    print(
        f"车辆: {vehicle.get('display_name')}, "
        f"VIN: {vehicle.get('vin')}, ID: {vehicle.get('id')}"
    )

    data = get_vehicle_data(token, vehicle)
    if not data:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(
                "<h1>已连接 API，但本次未能获取车辆详细数据（车辆可能休眠或需 Fleet API 权限）</h1>"
            )
        print("已生成占位 index.html")
        exit(0)

    generate_html(data, [], data.get("charge_state", {}))
    print("报告已生成: index.html")
