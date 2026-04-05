from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os

app = FastAPI()

# 解决跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 对话记忆（多轮对话）
memory = []
notes = []
MEMORY_LIMIT = 50
NOTE_LIMIT = 20

# 输入格式
class ChatInput(BaseModel):
    message: str

# 天气服务配置
# 官网地址：https://www.qweather.com
# 先尝试使用 qweather 官方 API，如无法请求则回退到 wttr.in 免费接口
DEFAULT_CITY = "广州"
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "737e888fabbe43d5919f56a49802f33f")
QWEATHER_HOSTS = ["https://devapi.qweather.com", "https://api.qweather.com"]

# 城市映射用于简单匹配用户查询
CITY_CODE = {
    "北京": "北京",
    "上海": "上海",
    "广州": "广州",
    "深圳": "深圳",
    "杭州": "杭州",
    "成都": "成都",
    "武汉": "武汉",
    "南京": "南京",
    "重庆": "重庆",
    "西安": "西安",
}

# 内部助手函数

def save_memory(role: str, text: str):
    memory.append({"role": role, "text": text})
    if len(memory) > MEMORY_LIMIT:
        memory.pop(0)


def save_note(text: str):
    notes.append(text)
    if len(notes) > NOTE_LIMIT:
        notes.pop(0)


def get_memory_text() -> str:
    if not memory:
        return "当前还没有对话记录。"
    return "\n".join([f"{item['role']}：{item['text']}" for item in memory])


def get_notes_text() -> str:
    if not notes:
        return "我还没有记住任何内容，请告诉我记住什么。"
    return "我记住了：\n" + "\n".join([f"{idx + 1}. {note}" for idx, note in enumerate(notes)])


def get_qweather_data(city_name: str):
    if not WEATHER_API_KEY:
        return {"error": "未配置 qweather API Key"}

    city = CITY_CODE.get(city_name, city_name or DEFAULT_CITY)
    encoded_city = requests.utils.requote_uri(city)
    for host in QWEATHER_HOSTS:
        url = f"{host}/v7/weather/now?location={encoded_city}&key={WEATHER_API_KEY}&lang=zh&unit=m"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if data.get("code") == "200":
                return {"service": "qweather", "type": "now", "data": data}
        except Exception:
            continue

    return {"error": "qweather API 请求失败或 Key/Host 不可用"}


def get_wttr_data(city_name: str):
    city = CITY_CODE.get(city_name, city_name or DEFAULT_CITY)
    encoded = requests.utils.requote_uri(city)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        data["service"] = "wttr"
        return data
    except Exception as e:
        return {"error": str(e)}


def get_weather_data(city_name: str):
    qdata = get_qweather_data(city_name)
    if "error" not in qdata:
        return qdata
    return get_wttr_data(city_name)


def get_now_weather(city_name: str) -> str:
    data = get_weather_data(city_name)
    if data is None or "error" in data:
        return f"⚠️ 天气查询失败：{data.get('error', '未知错误')}"

    if data.get("service") == "qweather":
        now = data["data"]["now"]
        basic = data["data"]["basic"]
        return (
            f"🌤 {basic['location']} 当前天气：\n"
            f"天气：{now['text']}\n"
            f"温度：{now['temp']}℃\n"
            f"风向风力：{now['windDir']} {now['windScale']}级\n"
            f"湿度：{now['humidity']}%"
        )

    current = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city_name or DEFAULT_CITY)
    desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
    temp = current.get("temp_C", "?")
    humidity = current.get("humidity", "?")
    wind = current.get("windspeedKmph", "?")
    feels = current.get("FeelsLikeC", "?")

    return (
        f"🌤 {area} 当前天气：\n"
        f"天气：{desc}\n"
        f"温度：{temp}℃（体感 {feels}℃）\n"
        f"风速：{wind} km/h\n"
        f"湿度：{humidity}%"
    )


def get_forecast_weather(city_name: str, days: int = 3) -> str:
    data = get_wttr_data(city_name)
    if data is None or "error" in data:
        return f"⚠️ 预报查询失败：{data.get('error', '未知错误')}"

    weather_list = data.get("weather", [])[:days]
    if not weather_list:
        return "⚠️ 无法获取天气预报，请稍后重试。"

    city = CITY_CODE.get(city_name, city_name or DEFAULT_CITY)
    forecast_lines = []
    for day in weather_list:
        date = day.get("date", "")
        text = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "")
        forecast_lines.append(
            f"{date}：{text}，{day.get('mintempC', '?')}~{day.get('maxtempC', '?')}℃"
        )

    return f"📅 {city} {days}天天气预报：\n" + "\n".join(forecast_lines)


def extract_city(user_msg: str) -> str:
    for city in CITY_CODE.keys():
        if city in user_msg:
            return city
    return DEFAULT_CITY


def is_weather_query(user_msg: str) -> bool:
    return "天气" in user_msg or "气温" in user_msg or "下雨" in user_msg or "晴" in user_msg


def is_forecast_query(user_msg: str) -> bool:
    return any(keyword in user_msg for keyword in ["预报", "明天", "后天", "三天", "未来"])


def extract_note_text(user_msg: str) -> str:
    markers = ["记住", "记下", "帮我记住", "帮我记下"]
    for marker in markers:
        if marker in user_msg:
            note = user_msg.split(marker, 1)[-1].strip()
            if note:
                return note
    return ""

# 智能体核心
@app.post("/agent")
async def agent_chat(input: ChatInput):
    user_msg = input.message.strip()
    save_memory("用户", user_msg)

    reply = ""

    if any(keyword in user_msg for keyword in ["记住", "记下", "帮我记住", "帮我记下"]):
        note = extract_note_text(user_msg)
        if note:
            save_note(note)
            reply = f"✅ 已记住：{note}"
        else:
            reply = "请告诉我你想记住的内容，例如：记住我喜欢学习Python。"

    elif any(keyword in user_msg for keyword in ["你记得", "还记得", "记得吗", "回忆"]):
        reply = get_notes_text()

    elif any(keyword in user_msg for keyword in ["忘记", "清空记忆", "清除记忆"]):
        notes.clear()
        reply = "✅ 我已清空记住的内容。"

    elif is_weather_query(user_msg):
        city = extract_city(user_msg)
        if is_forecast_query(user_msg):
            reply = get_forecast_weather(city, days=3)
        else:
            now_text = get_now_weather(city)
            forecast_text = get_forecast_weather(city, days=2)
            reply = f"{now_text}\n\n{forecast_text}"

    elif any(keyword in user_msg for keyword in ["任务", "待办"]):
        reply = (
            "✅ 已为你生成今日待办清单：\n"
            "1. 完成AI智能体作业\n"
            "2. 复习前后端连接知识\n"
            "3. 整理项目文档\n"
            "4. 提交GitHub仓库"
        )

    elif any(keyword in user_msg for keyword in ["计划", "安排"]):
        reply = (
            "📅 这里是一个高效学习计划：\n"
            "9:00-11:00 专业课程学习\n"
            "14:00-16:00 项目编码开发\n"
            "19:00-20:00 代码调试与优化\n"
            "20:30-21:30 学习总结与笔记整理"
        )

    else:
        reply = (
            "你好！我是AI任务助手，支持：\n"
            "1. 查询天气（例如：广州天气、北京明天预报）\n"
            "2. 记住内容（例如：记住我喜欢Python）\n"
            "3. 回忆我记住的内容（例如：你记得什么）"
        )

    save_memory("助手", reply)
    return {"reply": reply, "memory": get_memory_text(), "notes": notes}

@app.post("/clear")
async def clear_memory():
    memory.clear()
    notes.clear()
    return {"msg": "已清空对话历史和记忆"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
