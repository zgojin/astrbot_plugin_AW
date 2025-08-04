import asyncio
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from astrbot.api.all import *
from astrbot.api.event import filter

# 设置插件主目录
PLUGIN_DIR = os.path.join("data", "plugins", "astrbot_plugin_AnimeWife")
os.makedirs(PLUGIN_DIR, exist_ok=True)

# 配置文件目录
CONFIG_DIR = os.path.join(PLUGIN_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)

# 本地图片目录
IMG_DIR = os.path.join(PLUGIN_DIR, "img", "wife")
os.makedirs(IMG_DIR, exist_ok=True)

# 黑白大图目录
BW_GALLERY_DIR = os.path.join(PLUGIN_DIR, "bw_galleries")
os.makedirs(BW_GALLERY_DIR, exist_ok=True)
# 通用黑白大图路径（所有群共用）
COMMON_BW_GALLERY_PATH = os.path.join(BW_GALLERY_DIR, "common_bw_gallery.png")

# 最终图鉴目录
GALLERY_DIR = os.path.join(PLUGIN_DIR, "gallery")
os.makedirs(GALLERY_DIR, exist_ok=True)

# NTR 状态文件路径
NTR_STATUS_FILE = os.path.join(CONFIG_DIR, "ntr_status.json")
# NTR 次数限制文件路径
NTR_LIMIT_FILE = os.path.join(CONFIG_DIR, "ntr_limit.json")

# 图片的基础 URL
IMAGE_BASE_URL = "http://save.my996.top/?/img/"

# 创建线程池用于异步处理
executor = ThreadPoolExecutor(max_workers=2)

# 每人每天可牛老婆的次数
_ntr_max = 3
# 牛老婆的成功率
ntr_possibility = 0.20

# 全局NTR数据
ntr_statuses = {}  # NTR功能开关状态
ntr_limits = {}  # NTR次数限制，按群、用户、日期记录


def clean_old_ntr_data():
    """清理非当天的NTR计数数据，只保留今日记录"""
    global ntr_limits
    today = get_today()
    # 遍历所有群和用户，只保留当天的计数
    for group_id in list(ntr_limits.keys()):
        group_data = ntr_limits[group_id]
        for user_id in list(group_data.keys()):
            user_data = group_data[user_id]
            # 删除非今日的日期记录
            for date in list(user_data.keys()):
                if date != today:
                    del user_data[date]
            # 若用户当天无记录，可选择删除该用户条目
            if not user_data:
                del group_data[user_id]
        # 若群内无用户数据，可选择删除该群条目
        if not group_data:
            del ntr_limits[group_id]


def load_ntr_data():
    """加载NTR状态和次数限制数据，并清理历史记录"""
    global ntr_statuses, ntr_limits
    ntr_statuses = {}
    ntr_limits = {}

    # 加载NTR状态
    if os.path.exists(NTR_STATUS_FILE):
        try:
            with open(NTR_STATUS_FILE, "r", encoding="utf-8") as f:
                ntr_statuses = json.load(f)
        except Exception as e:
            print(f"加载NTR状态失败: {e}")
            ntr_statuses = {}

    # 加载NTR次数限制
    if os.path.exists(NTR_LIMIT_FILE):
        try:
            with open(NTR_LIMIT_FILE, "r", encoding="utf-8") as f:
                ntr_limits = json.load(f)
                # 兼容处理：升级旧格式数据
                ntr_limits = _upgrade_ntr_limit_format(ntr_limits)
        except Exception as e:
            print(f"加载NTR次数限制失败: {e}")
            ntr_limits = {}
    else:
        ntr_limits = {}

    # 关键：加载后清理历史数据，只保留当天计数
    clean_old_ntr_data()


def save_ntr_data():
    """保存NTR状态和次数限制数据"""
    try:
        # 保存NTR状态
        with open(NTR_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(ntr_statuses, f, ensure_ascii=False, indent=2)

        # 保存NTR次数限制
        with open(NTR_LIMIT_FILE, "w", encoding="utf-8") as f:
            json.dump(ntr_limits, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存NTR数据失败: {e}")


def _upgrade_ntr_limit_format(data):
    """
    将旧格式的NTR次数数据升级为新的日期关联格式。
    此函数具有幂等性，可以安全地处理已经是新格式的数据。
    旧格式: {'group_id': {'user_id': count_int}}
    新格式: {'group_id': {'user_id': {'date_str': count_int}}}
    """
    if not data:
        return data

    # 通过检查第一个用户记录的格式来判断是否需要转换
    try:
        first_group_data = next(iter(data.values()))
        # 处理群组存在但无用户记录的边缘情况
        if not first_group_data:
            return data
        first_user_record = next(iter(first_group_data.values()))
        # 如果记录值是字典，说明已经是新格式，无需转换
        if isinstance(first_user_record, dict):
            return data
    except (StopIteration, AttributeError):
        # 数据为空或结构不完整（例如，群里没人），无需转换
        return data

    # 确定是旧格式，执行转换
    new_data = {}
    today = get_today()
    for group_id, user_data in data.items():
        if not isinstance(user_data, dict):
            continue
        new_group_data = {}
        # 只处理值为整数的旧格式记录
        for user_id, count in user_data.items():
            if isinstance(count, int):
                new_group_data[user_id] = {today: count}
        new_data[group_id] = new_group_data
    return new_data


def get_today():
    """获取上海时区当日日期"""
    utc_now = datetime.utcnow()
    shanghai_time = utc_now + timedelta(hours=8)
    return shanghai_time.date().isoformat()


def parse_wife_name(wife_name: str) -> (str, str):
    """
    解析图片名字，提取角色名和来源
    支持两种格式：
    1. 来源.角色名.jpg
    2. 角色名.jpg/png
    """
    parts = wife_name.split(".")
    if len(parts) >= 3:
        # 新格式：来源.角色名.jpg
        source = parts[0]
        name = parts[1]
    else:
        # 旧格式：角色名.jpg/png 或 角色名.png
        name = parts[0]
        source = "未知"
    return name, source


def upgrade_unlocked_format(unlocked_list):
    """将旧格式的 unlocked 列表转换为包含解锁时间的对象数组"""
    today = get_today()
    return [{"wife_name": wife, "unlock_date": today} for wife in unlocked_list]


def get_wife_names_from_unlocked(unlocked):
    """从解锁列表中提取老婆名字列表"""
    return (
        [item["wife_name"] for item in unlocked] if isinstance(unlocked, list) else []
    )


def get_unlock_date(unlocked, wife_name):
    """获取指定老婆的解锁时间"""
    if not isinstance(unlocked, list):
        return None
    for item in unlocked:
        if item["wife_name"] == wife_name:
            return item.get("unlock_date")
    return None


@register(
    "wife_plugin",
    "长安某",
    "二次元老婆抽卡与图鉴插件",
    "1.5.2",
    "https://github.com/zgojin/astrbot_plugin_AW",
)
class WifePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.commands = {
            "抽老婆": self.animewife,
            "牛老婆": self.ntr_wife,
            "查老婆": self.search_wife,
            "切换ntr状态": self.switch_ntr,
            "群老婆图鉴": self.show_group_wife_gallery,
            "老婆图鉴": self.show_personal_wife_gallery,
        }
        self.admins = self.load_admins()

    def load_admins(self):
        """加载管理员列表"""
        try:
            with open(
                os.path.join("data", "cmd_config.json"), "r", encoding="utf-8-sig"
            ) as f:
                config = json.load(f)
                return config.get("admins_id", [])
        except:
            return []

    def parse_at_target(self, event):
        """解析消息中的@目标用户ID"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        return None

    def parse_target(self, event):
        """解析@目标或用户名，返回用户ID"""
        target_id = self.parse_at_target(event)
        if target_id:
            return target_id
        msg = event.message_str.strip()
        if msg.startswith(("牛老婆", "查老婆")):
            target_name = msg[len(msg.split()[0]) :].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                config = load_group_config(group_id)
                if config:
                    for user_id, user_data in config.items():
                        try:
                            nick_name = event.get_sender_name() or "未知用户"
                            if re.search(
                                re.escape(target_name), nick_name, re.IGNORECASE
                            ):
                                return user_id
                        except:
                            pass
        return None

    @event_message_type(EventMessageType.ALL)
    async def on_all_messages(self, event: AstrMessageEvent):
        """消息处理入口，检查并执行匹配的命令"""
        # 检查是否为群聊消息
        if not hasattr(event.message_obj, "group_id"):
            return

        group_id = event.message_obj.group_id
        message_str = event.message_str.strip()

        for command, func in self.commands.items():
            if command in message_str:
                async for result in func(event):
                    yield result
                break

    @filter.command("抽取老婆")
    async def animewife(self, event: AstrMessageEvent):
        """随机抽取一张二次元老婆"""
        group_id = event.message_obj.group_id
        if not group_id:
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请检查消息事件对象。")
            return

        wife_name = None
        today = get_today()
        config = load_group_config(group_id)

        # 初始化用户数据结构
        if str(user_id) not in config:
            config[str(user_id)] = {
                "current": {"wife_name": None, "date": ""},
                "unlocked": [],
                "nickname": nickname,
            }
        user_data = config[str(user_id)]

        # 检查当日老婆是否有效
        if user_data["current"]["date"] == today:
            wife_name = user_data["current"]["wife_name"]
        else:
            # 抽取新老婆
            if os.listdir(IMG_DIR):
                local_images = os.listdir(IMG_DIR)
                wife_name = random.choice(local_images)
            else:
                try:
                    response = requests.get(IMAGE_BASE_URL)
                    if response.status_code == 200:
                        image_list = response.text.splitlines()
                        wife_name = random.choice(image_list) if image_list else None
                    if not wife_name:
                        yield event.plain_result("图片列表为空，请稍后再试。")
                        return
                except:
                    yield event.plain_result("获取图片时发生错误，请稍后再试。")
                    return

            # 更新当日老婆
            user_data["current"] = {"wife_name": wife_name, "date": today}

            # 记录历史解锁（去重）
            unlocked_wives = get_wife_names_from_unlocked(user_data["unlocked"])
            if wife_name and wife_name not in unlocked_wives:
                user_data["unlocked"].append(
                    {"wife_name": wife_name, "unlock_date": today}
                )

        # 解析并发送结果
        name, source = parse_wife_name(wife_name)
        if source != "未知":
            text_message = (
                f"{nickname}，你今天的二次元老婆是来自《{source}》的{name}哒~ "
            )
        else:
            text_message = f"{nickname}，你今天的二次元老婆是{name}哒~"

        try:
            # 尝试发送图片
            if os.path.exists(os.path.join(IMG_DIR, wife_name)):
                with open(os.path.join(IMG_DIR, wife_name), "rb") as f:
                    image_data = f.read()
                chain = [Plain(text_message), Image.fromBytes(image_data)]
            else:
                image_url = IMAGE_BASE_URL + wife_name
                response = requests.get(image_url)
                if response.status_code == 200:
                    chain = [Plain(text_message), Image.fromBytes(response.content)]
                else:
                    chain = [
                        Plain(f"{text_message}\n图片加载失败，请检查图片链接是否有效。")
                    ]
        except:
            chain = [Plain(f"{text_message}\n图片加载失败，请稍后再试。")]

        try:
            yield event.chain_result(chain)
        except:
            yield event.plain_result(text_message)

        # 保存配置
        write_group_config(group_id, config)

    @filter.command("牛老婆")
    async def ntr_wife(self, event: AstrMessageEvent):
        """牛老婆 @user"""
        group_id = str(event.message_obj.group_id)
        if not group_id:
            yield event.plain_result("该功能仅支持群聊，请在群聊中使用。")
            return

        if not ntr_statuses.get(group_id, False):
            yield event.plain_result("NTR功能未开启！")
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请检查消息事件对象。")
            return

        # 每次操作前强制刷新当天日期，避免跨天问题
        today = get_today()
        # 获取用户今日NTR次数（明确从当天日期获取，默认0）
        group_ntr = ntr_limits.setdefault(str(group_id), {})
        user_ntr = group_ntr.setdefault(user_id, {})
        today_count = user_ntr.get(today, 0)

        if today_count >= _ntr_max:
            yield event.plain_result(
                f"{nickname}，你今天已经牛了{_ntr_max}次，明日再来吧~"
            )
            return

        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result(f"{nickname}，请指定一个要下手的目标~")
            return

        if user_id == target_id:
            yield event.plain_result(f"{nickname}，不能对自己下手哦！")
            return

        config = load_group_config(group_id)
        if not config:
            yield event.plain_result("未找到本群婚姻登记信息~")
            return

        if str(target_id) not in config:
            yield event.plain_result("对方还没有老婆哦~")
            return

        target_data = config[str(target_id)]
        if target_data["current"]["date"] != today:
            yield event.plain_result("对方的老婆已过期，换个目标吧~")
            return

        # 增加NTR次数并保存
        user_ntr[today] = today_count + 1
        save_ntr_data()

        if random.random() < ntr_possibility:
            target_wife = target_data["current"]["wife_name"]
            # 更新当前用户的老婆
            user_data = config.setdefault(
                str(user_id),
                {
                    "current": {"wife_name": None, "date": ""},
                    "unlocked": [],
                    "nickname": nickname,
                },
            )
            user_data["current"] = {"wife_name": target_wife, "date": today}
            # 记录历史解锁
            unlocked_wives = get_wife_names_from_unlocked(user_data["unlocked"])
            if target_wife and target_wife not in unlocked_wives:
                user_data["unlocked"].append(
                    {"wife_name": target_wife, "unlock_date": today}
                )
            # 清除目标用户的当日老婆
            target_data["current"] = {"wife_name": None, "date": ""}
            write_group_config(group_id, config)
            yield event.plain_result(f"{nickname}，恭喜你成功牛走了对方的老婆！")
        else:
            remaining = _ntr_max - (today_count + 1)
            yield event.plain_result(
                f"{nickname}，你的NTR计划失败了，还剩{remaining}次机会~"
            )

    @filter.command("查老婆")
    async def search_wife(self, event: AstrMessageEvent):
        """查老婆 @user"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("该功能仅支持群聊，请在群聊中使用。")
            return

        target_id = self.parse_target(event)
        today = get_today()

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请检查消息事件对象。")
            return

        target_id = target_id or user_id
        config = load_group_config(group_id)

        if not config or str(target_id) not in config:
            yield event.plain_result("未找到老婆信息！")
            return

        target_data = config[str(target_id)]
        if target_data["current"]["date"] != today:
            yield event.plain_result("查询的老婆已过期~")
            return

        wife_name = target_data["current"]["wife_name"]
        name, source = parse_wife_name(wife_name)
        target_nickname = target_data.get("nickname") or "用户"

        # 获取解锁时间
        unlock_date = get_unlock_date(target_data["unlocked"], wife_name)
        unlock_info = f"（解锁于{unlock_date}）" if unlock_date else ""

        if source != "未知":
            text_message = f"{target_nickname}的二次元老婆是{name}哒~ 来自《{source}》{unlock_info}"
        else:
            text_message = f"{target_nickname}的二次元老婆是{name}哒~{unlock_info}"

        try:
            # 尝试发送图片
            if os.path.exists(os.path.join(IMG_DIR, wife_name)):
                with open(os.path.join(IMG_DIR, wife_name), "rb") as f:
                    image_data = f.read()
                chain = [Plain(text_message), Image.fromBytes(image_data)]
            else:
                image_url = IMAGE_BASE_URL + wife_name
                response = requests.get(image_url)
                if response.status_code == 200:
                    chain = [Plain(text_message), Image.fromBytes(response.content)]
                else:
                    chain = [
                        Plain(f"{text_message}\n图片加载失败，请检查图片链接是否有效。")
                    ]
        except:
            chain = [Plain(f"{text_message}\n图片加载失败，请稍后再试。")]

        try:
            yield event.chain_result(chain)
        except:
            yield event.plain_result(text_message)

    @filter.command("切换ntr状态")
    async def switch_ntr(self, event: AstrMessageEvent):
        """切换是否进入NTR状态"""
        group_id = str(event.message_obj.group_id)
        if not group_id:
            yield event.plain_result("该功能仅支持群聊，请在群聊中使用。")
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请检查消息事件对象。")
            return

        if user_id not in self.admins:
            yield event.plain_result(f"{nickname}，你没有权限切换NTR功能状态。")
            return

        ntr_statuses[group_id] = not ntr_statuses.get(group_id, False)
        save_ntr_data()
        status_text = "开启" if ntr_statuses[group_id] else "关闭"
        yield event.plain_result(f"NTR功能已{status_text}，请注意群内和谐~")

    @filter.command("群老婆图鉴")
    async def show_group_wife_gallery(self, event: AstrMessageEvent):
        """查看群里已经解锁的老婆"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("该功能仅支持群聊，请在群聊中使用。")
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请重试。")
            return

        # 此处假设anime_wife_collage模块存在，实际使用时需确保该模块可用
        try:
            from .anime_wife_collage import (
                create_or_update_wife_gallery,
                get_all_wife_images,
                get_unlocked_wives,
            )
        except Exception as e:
            print(f"加载图鉴模块失败: {e}")
            yield event.plain_result("老婆图鉴功能加载失败，请稍后再试。")
            return

        # 在后台线程中执行耗时的图鉴生成操作
        loop = asyncio.get_event_loop()
        gallery_path = os.path.join(GALLERY_DIR, f"gallery_{group_id}.png")

        try:
            gallery_path = await loop.run_in_executor(
                executor,
                create_or_update_wife_gallery,
                str(group_id),
                IMG_DIR,
                CONFIG_DIR,
                BW_GALLERY_DIR,
                gallery_path,
            )

            # 检查图片是否生成成功
            if not os.path.exists(gallery_path):
                yield event.plain_result("图鉴生成失败，未找到图片文件。")
                return

            # 获取已解锁数量和总数量
            all_wives = get_all_wife_images(IMG_DIR)
            unlocked_wives = get_unlocked_wives(str(group_id), CONFIG_DIR)
            unlocked_count = len(unlocked_wives)
            total_count = len(all_wives)

            # 发送图鉴图片
            with open(gallery_path, "rb") as f:
                image_data = f.read()

            msg = (
                f"{nickname}，本群老婆图鉴来啦~ 已解锁: {unlocked_count}/{total_count}"
            )
            yield event.chain_result([Plain(msg), Image.fromBytes(image_data)])

        except Exception as e:
            print(f"生成图鉴失败: {e}")
            yield event.plain_result("生成图鉴失败，请稍后再试。")

    @filter.command("老婆图鉴")
    async def show_personal_wife_gallery(self, event: AstrMessageEvent):
        """查看已经解锁的老婆"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("该功能仅支持群聊，请在群聊中使用。")
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name() or "用户"
        except:
            yield event.plain_result("无法获取用户信息，请重试。")
            return

        config = load_group_config(group_id)
        if str(user_id) not in config:
            yield event.plain_result("你还没有解锁任何老婆哦~")
            return

        user_data = config[str(user_id)]
        unlocked_wives = get_wife_names_from_unlocked(user_data["unlocked"])

        if not unlocked_wives:
            yield event.plain_result("你还没有解锁任何老婆哦~")
            return

        try:
            from .anime_wife_collage import create_personal_wife_gallery
        except Exception as e:
            print(f"加载个人图鉴模块失败: {e}")
            yield event.plain_result("个人老婆图鉴功能加载失败，请稍后再试。")
            return

        loop = asyncio.get_event_loop()
        personal_gallery_path = os.path.join(
            GALLERY_DIR, f"personal_gallery_{user_id}.png"
        )

        try:
            personal_gallery_path = await loop.run_in_executor(
                executor,
                create_personal_wife_gallery,
                unlocked_wives,
                IMG_DIR,
                personal_gallery_path,
            )

            if not os.path.exists(personal_gallery_path):
                yield event.plain_result("个人图鉴生成失败，未找到图片文件。")
                return

            with open(personal_gallery_path, "rb") as f:
                image_data = f.read()

            msg = f"{nickname}，你的个人老婆图鉴来啦~ 已解锁: {len(unlocked_wives)}"
            yield event.chain_result([Plain(msg), Image.fromBytes(image_data)])

        except Exception as e:
            print(f"生成个人图鉴失败: {e}")
            yield event.plain_result("生成个人图鉴失败，请稍后再试。")


# 加载群配置数据，兼容旧格式
def load_group_config(group_id: str):
    filename = os.path.join(CONFIG_DIR, f"{group_id}.json")
    try:
        with open(filename, encoding="utf-8") as f:
            config = json.load(f)
            # 兼容旧格式数据
            for user_id in list(config.keys()):
                user_data = config[user_id]
                if isinstance(user_data, list):
                    # 旧格式：列表格式
                    if len(user_data) >= 2:
                        old_wife = user_data[0]
                        old_date = user_data[1]
                        old_nick = user_data[2] if len(user_data) > 2 else "用户"
                        config[user_id] = {
                            "current": {"wife_name": old_wife, "date": old_date},
                            "unlocked": [
                                {"wife_name": old_wife, "unlock_date": old_date}
                            ],
                            "nickname": old_nick,
                        }
                else:
                    # 检查 unlocked 格式是否需要升级
                    if "unlocked" in user_data and isinstance(
                        user_data["unlocked"], list
                    ):
                        if user_data["unlocked"] and isinstance(
                            user_data["unlocked"][0], str
                        ):
                            # 升级旧格式的 unlocked 列表
                            user_data["unlocked"] = upgrade_unlocked_format(
                                user_data["unlocked"]
                            )
            return config
    except Exception as e:
        print(f"加载群配置失败: {e}")
        return {}


# 写入群配置数据
def write_group_config(group_id: str, config: dict):
    config_file = os.path.join(CONFIG_DIR, f"{group_id}.json")
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存群配置失败: {e}")


# 程序启动时加载NTR数据
load_ntr_data()
