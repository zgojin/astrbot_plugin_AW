from astrbot.api.all import *
from datetime import datetime, timedelta
import random
import os
import re
import json
import requests


# 设置插件主目录
PLUGIN_DIR = os.path.join('data', 'plugins', 'astrbot_plugin_AnimeWife')
os.makedirs(PLUGIN_DIR, exist_ok=True)

# 配置文件目录
CONFIG_DIR = os.path.join(PLUGIN_DIR, 'config')
os.makedirs(CONFIG_DIR, exist_ok=True)

# 本地图片目录
IMG_DIR = os.path.join(PLUGIN_DIR, 'img', 'wife')
os.makedirs(IMG_DIR, exist_ok=True)

# NTR 状态文件路径
NTR_STATUS_FILE = os.path.join(CONFIG_DIR, 'ntr_status.json')

# 图片的基础 URL
IMAGE_BASE_URL = 'http://save.my996.top/?/img/'


# 新增函数：获取上海时区当日日期
def get_today():
    utc_now = datetime.utcnow()
    shanghai_time = utc_now + timedelta(hours=8)
    return shanghai_time.date().isoformat()


# 新增函数：解析图片名字，提取角色名和来源
def parse_wife_name(wife_name: str) -> (str, str):
    # 图片名字格式为：来源.角色名.jpg 或 角色名.jpg/png
    parts = wife_name.split('.')
    if len(parts) >= 3:
        # 新格式：来源.角色名.jpg
        source = parts[0]
        name = parts[1]
    else:
        # 旧格式：角色名.jpg/png 或 角色名.png
        name = parts[0]
        source = '未知'
    return name, source


# 载入 NTR 状态
def load_ntr_statuses():
    global ntr_statuses
    # 检查文件是否存在
    if not os.path.exists(NTR_STATUS_FILE):
        # 文件不存在，则创建空的状态文件
        with open(NTR_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)
        ntr_statuses = {}
    else:
        # 文件存在，读取内容到 ntr_statuses
        with open(NTR_STATUS_FILE, 'r', encoding='utf-8') as f:
            ntr_statuses = json.load(f)


# 在程序启动时调用
load_ntr_statuses()


def save_ntr_statuses():
    with open(NTR_STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ntr_statuses, f, ensure_ascii=False, indent=4)


@register("wife_plugin", "长安某", "群老婆插件", "1.1.0", "url")
class WifePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.commands = {
            "抽老婆": self.animewife,
            "牛老婆": self.ntr_wife,
            "查老婆": self.search_wife,
            "切换ntr开关状态": self.switch_ntr
        }
        self.admins = self.load_admins()

    def load_admins(self):
        """加载管理员列表"""
        try:
            with open(os.path.join('data', 'cmd_config.json'), 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
                return config.get('admins_id', [])
        except Exception as e:
            self.context.logger.error(f"加载管理员列表失败: {str(e)}")
            return []

    def parse_at_target(self, event):
        """解析@目标"""
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                return str(comp.qq)
        return None

    def parse_target(self, event):
        """解析@目标或用户名"""
        target_id = self.parse_at_target(event)
        if target_id:
            return target_id
        msg = event.message_str.strip()
        if msg.startswith("牛老婆") or msg.startswith("查老婆"):
            target_name = msg[len(msg.split()[0]):].strip()
            if target_name:
                group_id = str(event.message_obj.group_id)
                config = load_group_config(group_id)
                if config:
                    for user_id, user_data in config.items():
                        try:
                            # 使用 event.get_sender_name() 获取昵称
                            nick_name = event.get_sender_name()
                            if re.search(re.escape(target_name), nick_name, re.IGNORECASE):
                                return user_id
                        except Exception as e:
                            self.context.logger.error(f'获取群成员信息出错: {e}')
        return None

    @event_message_type(EventMessageType.ALL)
    async def on_all_messages(self, event: AstrMessageEvent):
        # 检查是否为群聊消息
        if not hasattr(event.message_obj, "group_id"):
            return  # 如果不是群聊消息，直接返回，不做处理

        group_id = event.message_obj.group_id
        message_str = event.message_str.strip()

        for command, func in self.commands.items():
            if command in message_str:
                async for result in func(event):
                    yield result
                break

    async def animewife(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        if not group_id:
            return  # 在私聊中不提示信息，直接返回

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name()
        except AttributeError:
            yield event.plain_result('无法通过 event.get_sender_id() 获取用户 ID，请检查消息事件对象。')
            return

        wife_name = None
        today = get_today()
        config = load_group_config(group_id)

        if config and str(user_id) in config:
            if config[str(user_id)][1] == today:
                wife_name = config[str(user_id)][0]
            else:
                del config[str(user_id)]

        if wife_name is None:
            if config:
                for record_id in list(config):
                    if config[record_id][1] != today:
                        del config[record_id]
            # 先尝试从本地文件夹获取图片
            local_images = os.listdir(IMG_DIR)
            if local_images:
                wife_name = random.choice(local_images)
            else:
                try:
                    # 本地没有图片，从网址获取
                    response = requests.get(IMAGE_BASE_URL)
                    if response.status_code == 200:
                        image_list = response.text.splitlines()
                        wife_name = random.choice(image_list)
                    else:
                        yield event.plain_result('无法获取图片列表，请稍后再试。')
                        return
                except Exception as e:
                    yield event.plain_result(f'获取图片时发生错误: {str(e)}')
                    return

        # 解析图片名字，提取角色名和来源
        name, source = parse_wife_name(wife_name)
        if source != '未知':
            text_message = f'{nickname}，你今天的二次元老婆是来自《{source}》的{name}哒~ '
        else:
            text_message = f'{nickname}，你今天的二次元老婆是{name}哒~'

        if os.path.exists(os.path.join(IMG_DIR, wife_name)):
            # 本地有该图片，从本地发送
            image_path = os.path.join(IMG_DIR, wife_name)
            chain = [
                Plain(text_message),
                Image.fromFileSystem(image_path)
            ]
        else:
            # 本地没有该图片，从 URL 发送
            image_url = IMAGE_BASE_URL + wife_name
            chain = [
                Plain(text_message),
                Image.fromURL(image_url)
            ]

        try:
            yield event.chain_result(chain)
        except Exception as e:
            self.context.logger.error(f'发送老婆图片时发生错误{type(e)}')
            yield event.plain_result(text_message)

        # 修改此处，将用户名也存入配置文件
        write_group_config(group_id, user_id, wife_name, get_today(), nickname, config)

    async def ntr_wife(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result('该功能仅支持群聊，请在群聊中使用。')
            return

        if not ntr_statuses.get(group_id, False):
            yield event.plain_result('牛老婆功能未开启！')
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name()
        except AttributeError:
            yield event.plain_result('无法通过 event.get_sender_id() 获取用户 ID，请检查消息事件对象。')
            return

        if user_id not in ntr_lmt:
            ntr_lmt[user_id] = 0
        if ntr_lmt[user_id] >= _ntr_max:
            yield event.plain_result(f'{nickname}，{ntr_max_notice}')
            return

        target_id = self.parse_target(event)
        if not target_id:
            yield event.plain_result(f'{nickname}，请指定一个要下手的目标')
            return

        if user_id == target_id:
            yield event.plain_result(f'{nickname}，不能牛自己')
            return

        config = load_group_config(group_id)
        if not config:
            yield event.plain_result('没有找到本群婚姻登记信息')
            return

        if str(target_id) not in config:
            yield event.plain_result('需要对方有老婆才能牛')
            return

        today = get_today()
        if config[str(target_id)][1] != today:
            yield event.plain_result('对方的老婆已过期，您也不想要过期的老婆吧')
            return

        ntr_lmt[user_id] += 1
        if random.random() < ntr_possibility:
            target_wife = config[str(target_id)][0]
            del config[str(target_id)]
            config.pop(str(user_id), None)
            write_group_config(group_id, user_id, target_wife, today, nickname, config)
            yield event.plain_result(f'{nickname}，你的阴谋已成功！')
        else:
            yield event.plain_result(
                f'{nickname}，你的阴谋失败了，黄毛被干掉了！你还有{_ntr_max - ntr_lmt[user_id]}次机会')

    async def search_wife(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result('该功能仅支持群聊，请在群聊中使用。')
            return

        target_id = self.parse_target(event)
        today = get_today()
        wife_name = None

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name()
        except AttributeError:
            yield event.plain_result('无法通过 event.get_sender_id() 获取用户 ID，请检查消息事件对象。')
            return

        target_id = target_id or user_id

        config = load_group_config(group_id)
        if not config:
            yield event.plain_result('群婚姻信息不存在！')
            return

        if str(target_id) not in config:
            yield event.plain_result('未找到老婆信息！')
            return

        if config[str(target_id)][1] != today:
            yield event.plain_result('查询的老婆已过期')
            return

        wife_name = config[str(target_id)][0]
        name, source = parse_wife_name(wife_name)  # 解析图片名字，提取角色名和来源

        # 尝试从配置文件中获取用户名
        target_nickname = config.get(str(target_id), [None, None, target_id])[2]

        if source != '未知':
            text_message = f'{target_nickname}的二次元老婆是{name}哒~ 来自《{source}》'
        else:
            text_message = f'{target_nickname}的二次元老婆是{name}哒~'

        if os.path.exists(os.path.join(IMG_DIR, wife_name)):
            # 本地有该图片，从本地发送
            image_path = os.path.join(IMG_DIR, wife_name)
            chain = [
                Plain(text_message),
                Image.fromFileSystem(image_path)
            ]
        else:
            # 本地没有该图片，从 URL 发送
            image_url = IMAGE_BASE_URL + wife_name
            chain = [
                Plain(text_message),
                Image.fromURL(image_url)
            ]

        try:
            yield event.chain_result(chain)
        except Exception as e:
            self.context.logger.error(f'发送老婆图片时发生错误{type(e)}')
            yield event.plain_result(text_message)

    async def switch_ntr(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result('该功能仅支持群聊，请在群聊中使用。')
            return

        try:
            user_id = str(event.get_sender_id())
            nickname = event.get_sender_name()
        except AttributeError:
            yield event.plain_result('无法通过 event.get_sender_id() 获取用户 ID，请检查消息事件对象。')
            return

        if user_id not in self.admins:
            yield event.plain_result(f'{nickname}，你没有权限切换NTR功能状态。')
            return

        ntr_statuses[group_id] = not ntr_statuses.get(group_id, False)
        save_ntr_statuses()
        load_ntr_statuses()
        status_text = '开启' if ntr_statuses[group_id] else '关闭'
        yield event.plain_result(f'{nickname}，NTR功能已{status_text}')


# 每人每天可牛老婆的次数
_ntr_max = 3
ntr_lmt = {}
# 当超出次数时的提示
ntr_max_notice = f'为防止牛头人泛滥，一天最多可牛{_ntr_max}次，请明天再来吧~'
# 牛老婆的成功率
ntr_possibility = 0.20

# 用来存储所有群组的 NTR 状态
ntr_statuses = {}

# 加载 JSON 数据
def load_group_config(group_id: str):
    filename = os.path.join(CONFIG_DIR, f'{group_id}.json')
    try:
        with open(filename, encoding='utf8') as f:
            config = json.load(f)
            # 检查配置文件是否为旧格式
            for user_id, user_data in config.items():
                if len(user_data) < 3:
                    # 旧格式，这里简单假设无法获取用户名，用 ID 代替
                    user_data.append(user_id)
            return config
    except (FileNotFoundError, json.JSONDecodeError):
        return None

# 增加用户名参数
def write_group_config(group_id: str, link_id: str, wife_name: str, date: str, nickname: str, config):
    config_file = os.path.join(CONFIG_DIR, f'{group_id}.json')
    if config is not None:
        config[link_id] = [wife_name, date, nickname]
    else:
        config = {link_id: [wife_name, date, nickname]}
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False)
