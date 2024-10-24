import json
import os
import re
import random
from nonebot import require
from pathlib import Path

require("nonebot_plugin_localstore")
import nonebot_plugin_localstore as store
from datetime import datetime
from nonebot import on_message
from nonebot import on_command
from nonebot import get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, Event, MessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.rule import to_me

SUPERUSERS = get_driver().config.superusers
__plugin_meta__ = PluginMetadata(
    name="机厅",
    description="本地机厅管理和人数上报",
    usage="发送 机厅 help 查看帮助",
    type="application",
    supported_adapters={"~onebot.v11"},
    homepage="https://github.com/Onimaimai/nonebot-plugin-jtj",
)

plugin_data_dir: Path = store.get_plugin_data_dir()
# 文件路径
ARCADE_DATA_FILE: Path = store.get_plugin_data_file("arcade_data.json")
STATE_FILE: Path = store.get_plugin_data_file("state.json")
GROUP_REGION_FILE: Path = store.get_plugin_data_file("group_region.json")

# 创建文件（如果不存在）
for file_path in [ARCADE_DATA_FILE, STATE_FILE]:
    if not file_path.exists():
        file_path.write_text('{}', encoding='utf-8')
            

def load_arcade_data():
    """加载 arcade_data.json 文件中的数据"""
    global current_arcade_data  # 使用全局变量存储当前数据
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            current_arcade_data = json.load(file)
    except FileNotFoundError:
        current_arcade_data = []
    return current_arcade_data
      
# 用于存储最新加载的机厅数据
EMPTY_STATE = load_arcade_data()


def get_all_regions():
    """获取所有存在的地区列表"""
    return list(set([arcade["region"] for arcade in current_arcade_data]))

  
help_handler = on_command("机厅 help", priority=10, block=True)

@help_handler.handle()
async def handle_help(bot: Bot, event: GroupMessageEvent):
    help_message = (
        "地区列表\n"
        "绑定机厅<地区>\n"
        "查询简称<名称><地区>\n"
        "添加机厅<名称><地区><简称>\n"
        "删除机厅<名称><地区>\n"
        "添加简称<名称><地区><简称>\n"
        "删除简称<名称><地区><简称>\n"
        "解绑机厅\n"
        "随个机厅/去哪勤/勤哪/qn\n"
        "机厅几/jtj/JTJ\n"
        "<简称>几/j/J\n"
        "<简称>数字/+-数字\n"
        "重置人数"
    )
    await help_handler.send(help_message)

    
region_list_handler = on_command("地区列表", priority=10, block=True)

@region_list_handler.handle()
async def handle_region_list(bot: Bot, event: GroupMessageEvent):
    # 获取所有可用地区
    regions = get_all_regions()
    
    if not regions:
        await region_list_handler.send("当前没有可用的地区")
        return
    
    # 格式化地区列表
    region_list = "、".join(regions)
    message = f"地区列表：\n{region_list}"
    
    await region_list_handler.send(message)


reset_handler = on_command("重置人数", priority=10, block=True)
resetall_handler = on_command("重置机厅", priority=10, block=True)

@reset_handler.handle()
async def handle_reset(bot: Bot, event: Event):
    group_id = event.group_id
    user_id = event.get_user_id()
    
    # 检查用户是否是群主、管理员或超级用户
    member = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
    if member['role'] not in ['owner', 'admin'] and user_id not in SUPERUSERS:
        await reset_handler.send("您没有权限执行此操作")
        return

    # 读取当前群组绑定的地区
    group_region = read_group_region()
    if str(group_id) not in group_region:
        await reset_handler.send("该群组未绑定地区，无法重置机厅人数")
        return

    region_name = group_region[str(group_id)]
    
    # 调用重置函数
    reset_state(region_name)
    sync_arcade_data()
    await reset_handler.send("本群机厅人数已重置")
            
    
@resetall_handler.handle()
async def handle_resetall(bot: Bot, event: Event):
    user_id = event.get_user_id()
    
    if user_id not in SUPERUSERS:
        await reset_handler.send("您没有权限执行此操作")
        return
    
    # 调用重置函数
    reset_all_states()
    sync_arcade_data()
    await resetall_handler.send("所有机厅人数已重置")
    
            
def read_state():
    try:
        with STATE_FILE.open('r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        STATE_FILE.write_text(json.dumps(EMPTY_STATE, ensure_ascii=False, indent=2), encoding='utf-8')
        return EMPTY_STATE

def save_state(arcades):
    with STATE_FILE.open('w', encoding='utf-8') as file:
        json.dump(arcades, file, ensure_ascii=False, indent=2)


def read_group_region():
    try:
        with GROUP_REGION_FILE.open('r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_group_region(group_region):
    with GROUP_REGION_FILE.open('w', encoding='utf-8') as file:
        json.dump(group_region, file, ensure_ascii=False, indent=2)


def reset_state(region_name):
    updated_data = []
    
    for arcade in EMPTY_STATE:
        if arcade["region"] == region_name:  # 只重置特定地区的机厅
            reset_arcade = {
                "primary_keyword": arcade["primary_keyword"],
                "keywords": arcade["keywords"],
                "peopleCount": 0,
                "updatedBy": "无",
                "lastUpdatedAt": "04:00:00",
                "region": arcade["region"]  # 确保包含地区
            }
            updated_data.append(reset_arcade)

    # 将更新后的数据写回文件
    with open(STATE_FILE, 'w', encoding='utf-8') as file:
        json.dump(updated_data, file, ensure_ascii=False, indent=2)

    sync_arcade_data()
    print("机厅人数已重置")


def reset_all_states():
    updated_data = []

    for arcade in EMPTY_STATE:
        reset_arcade = {
            "primary_keyword": arcade["primary_keyword"],
            "keywords": arcade["keywords"],
            "peopleCount": 0,
            "updatedBy": "无",
            "lastUpdatedAt": "04:00:00",
            "region": arcade["region"]  # 确保包含地区
        }
        updated_data.append(reset_arcade)

    # 将更新后的数据写回文件
    with open(STATE_FILE, 'w', encoding='utf-8') as file:
        json.dump(updated_data, file, ensure_ascii=False, indent=2)

    sync_arcade_data()
    print("所有地区的机厅人数已重置")

    
    
# 获取 APScheduler 定时器
scheduler = require("nonebot_plugin_apscheduler").scheduler

@scheduler.scheduled_job("cron", hour=4, minute=0)
async def scheduled_task():
    reset_all_states()  # 调用重置状态的函数
    
  	
    
jtj_handler = on_command("jtj", aliases={"机厅几","JTJ"}, priority=10, block=True)

@jtj_handler.handle()
async def handle_jtj(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    group_region = read_group_region()

    # 检查群组是否有绑定地区
    if str(group_id) not in group_region:
        await jtj_handler.send("请发送：绑定机厅<地区>")
        return
    
    region_name = group_region[str(group_id)]
    
    # 从 state.json 中读取机厅数据
    arcades = read_state()

    # 筛选出属于该地区的机厅
    region_arcades = [arcade for arcade in arcades if arcade['region'] == region_name]

    if not region_arcades:
        await jtj_handler.send(f"未找到地区 {region_name} 的机厅数据")
        return

    # 格式化机厅信息并发送
    response_message = format_arcades_message(region_arcades, region_name)
    await jtj_handler.send(response_message)

# 保持原来的格式化方法不变
def format_arcades_message(arcades, region):
    message_lines = []
    
    for arcade in arcades:
        if region == arcade['region']:
            line = f"{arcade['primary_keyword']}：{arcade['peopleCount']}人"
            message_lines.append(line)
    return "\n".join(message_lines)
    
  
arcade_handler = on_message(priority=999)
@arcade_handler.handle()
async def handle_arcade(bot: Bot, event: GroupMessageEvent):
    arcades = read_state()
    group_id = event.group_id
    group_region = read_group_region().get(str(group_id))

    message = event.get_message().extract_plain_text().strip()
    user_info = await bot.get_group_member_info(group_id=group_id, user_id=event.user_id)
    user_nickname = user_info.get('nickname', '') + "(" + event.get_user_id() + ")"
    
    response = get_response(message, user_nickname, arcades, group_region)
    if response:
        await arcade_handler.send(response)
    save_state(arcades)


def get_response(message, user_nickname, arcades, group_region):
    
    # 如果绑定了地区，过滤出绑定地区的机厅
    region_arcades = [arcade for arcade in arcades if arcade["region"] == group_region]

    for arcade in region_arcades:
        for keyword in arcade["keywords"]:
            if message.startswith(keyword):
                updated = update_arcade_people_count(message, user_nickname, arcade, keyword)
                if updated:
                    save_state(arcades)
                    return f"更新成功！\n{arcade['primary_keyword']}\n当前：{arcade['peopleCount']}人"
                elif keyword + "几" in message or keyword + "j" in message or keyword + "J" in message:
                    return f"{arcade['primary_keyword']}\n当前：{arcade['peopleCount']}人\n\n上报：{arcade['updatedBy']}\n时间：{arcade['lastUpdatedAt']}"
    return None

  

def update_arcade_people_count(message, user_nickname, arcade, keyword):
    # 使用正则表达式来匹配消息中的数字
    match = re.search(f"{keyword}(\+|\-)?(\d+)", message)
    if not match:
        return False
    # 提取操作符和数字
    operator, number_str = match.groups()
    number = int(number_str)
    if operator == "+":
        arcade["peopleCount"] += number
    elif operator == "-":
        arcade["peopleCount"] -= number
    else:
        arcade["peopleCount"] = number
    arcade["updatedBy"] = user_nickname
    arcade["lastUpdatedAt"] = datetime.now().strftime("%H:%M:%S")
    return True  # 表示更新成功
        
        
# 将新的机厅数据与已有的人数数据合并，并删除不在 arcade_data.json 中的机厅
def sync_arcade_data():
    """将新的机厅数据与已有的人数数据合并，并删除不在 arcade_data.json 中的机厅"""
    # 读取当前 state.json 的数据
    current_data = read_state()

    # 构建一个以 "primary_keyword" 为键的字典，便于后续合并
    current_data_map = {arcade["primary_keyword"]: arcade for arcade in current_data}

    # 用来存储同步后的数据
    updated_data = []

    # 从 arcade_data.json 中获取所有的机厅数据
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            arcade_data = json.load(file)
    except FileNotFoundError:
        arcade_data = []

    # 获取所有机厅的关键词列表
    arcade_primary_keywords = [arcade["primary_keyword"] for arcade in arcade_data]

    # 遍历 arcade_data.json 中的机厅数据
    for arcade in arcade_data:
        primary_keyword = arcade["primary_keyword"]

        # 如果 state.json 中有这个机厅，保留它的人数数据
        if primary_keyword in current_data_map:
            existing_arcade = current_data_map[primary_keyword]
            arcade["peopleCount"] = existing_arcade.get("peopleCount", 0)
            arcade["updatedBy"] = existing_arcade.get("updatedBy", "无")
            arcade["lastUpdatedAt"] = existing_arcade.get("lastUpdatedAt", "04:00:00")
        else:
            # 如果是新的机厅，初始化人数数据
            arcade["peopleCount"] = 0
            arcade["updatedBy"] = "无"
            arcade["lastUpdatedAt"] = "04:00:00"

        updated_data.append(arcade)

    # 删除 state.json 中不再存在于 arcade_data.json 的机厅
    updated_data = [arcade for arcade in updated_data if arcade["primary_keyword"] in arcade_primary_keywords]

    # 将合并后的数据写回到 state.json 文件
    with open(STATE_FILE, 'w', encoding='utf-8') as file:
        json.dump(updated_data, file, ensure_ascii=False, indent=2)

    print("同步成功，已将机厅数据更新到 state.json")

    # 重新加载最新的 arcade_data.json 数据，确保新机厅和地区立即生效
    load_arcade_data()
    print("缓存已更新，新的机厅和地区已生效")

    
# 定义同步指令
sync_handler = on_command("更新机厅", priority=10, block=True)

@sync_handler.handle()
async def handle_sync(bot: Bot, event: GroupMessageEvent):
    user_id = event.get_user_id()

    # 如果用户不是超级用户，禁止同步
    if user_id not in SUPERUSERS:
        await sync_handler.send("您没有权限执行此操作")
        return

    # 调用同步函数
    sync_arcade_data()

    await sync_handler.send("机厅数据已更新！")
        

# 命令用于绑定地区
bind_region_handler = on_command("绑定机厅", priority=10, block=True)

@bind_region_handler.handle()
async def handle_bind_region(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    message = event.get_message().extract_plain_text().strip()
    region_name = message.replace("绑定机厅", "").strip()  # 去掉命令部分，提取地区名
    
    if not region_name:
        await bind_region_handler.send("请输入地区：\n绑定机厅<地区名>")
        return
    
    # 获取所有有效的地区
    valid_regions = get_all_regions()
    # 检查用户输入的地区是否有效
    if region_name not in valid_regions:
        # 将有效地区列表格式化为字符串
        available_regions = "、".join(valid_regions)
        await bot.send(event, f"绑定失败：地区 {region_name} 不存在！\n地区列表：\n{available_regions}")
        return
    
    group_region = read_group_region()
    group_region[str(group_id)] = region_name  # 将群组与地区绑定
    save_group_region(group_region)

    await bind_region_handler.send(f"已绑定机厅地区：{region_name}")

    
unbind_region_handler = on_command("解绑机厅", priority=10, block=True)

@unbind_region_handler.handle()
async def handle_unbind_region(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    group_region = read_group_region()

    if str(group_id) not in group_region:
        await unbind_region_handler.send("本群无需解绑")
        return

    del group_region[str(group_id)]  # 删除该群的绑定记录
    save_group_region(group_region)

    await unbind_region_handler.send("本群机厅已解绑")

    
# 新增查询简称命令处理器
query_short_name_handler = on_command("查询简称", priority=10, block=True)

@query_short_name_handler.handle()
async def handle_query_short_name(bot: Bot, event: GroupMessageEvent):
    message = event.get_message().extract_plain_text().strip()
    args = message.replace("查询简称", "").strip().split()
    
    if len(args) < 2:
        await query_short_name_handler.send("请输入要查询简称的机厅：\n查询简称<名称><地区>")
        return
    
    primary_keyword = args[0]
    region_name = args[1]

    arcades = read_state()
    arcade = next((arcade for arcade in arcades if arcade['primary_keyword'] == primary_keyword and arcade['region'] == region_name), None)

    if arcade is None:
        await query_short_name_handler.send(f"未找到简称\n机厅：{primary_keyword}\n地区：{region_name}")
        return
    
    keywords = arcade.get("keywords", [])
    if not keywords:
        await query_short_name_handler.send(f"机厅：{primary_keyword}\n地区：{region_name}\n没有简称")
    else:
        keywords_list = "、".join(keywords)
        await query_short_name_handler.send(f"机厅：{primary_keyword}\n地区：{region_name}\n简称：{keywords_list}")

        
        

# 命令：添加机厅
add_arcade_handler = on_command("添加机厅", priority=10, block=True)

@add_arcade_handler.handle()
async def handle_add_arcade(bot: Bot, event: GroupMessageEvent):
    # 获取消息内容
    message = event.get_message().extract_plain_text().strip()
    
    # 提取 primary_keyword、region、keywords
    args = message.replace("添加机厅", "").strip().split()
    
    if len(args) < 3:
        await add_arcade_handler.send("格式错误：\n添加机厅<名称><地区><简称>")
        return
    
    primary_keyword = args[0]
    region = args[1]
    keywords = args[2:]

    # 构造新机厅信息
    new_arcade = {
        "primary_keyword": primary_keyword,
        "keywords": keywords,
        "peopleCount": 0,
        "updatedBy": "无",
        "lastUpdatedAt": "04:00:00",
        "region": region
    }

    # 读取 JSON 文件并添加新机厅
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            arcade_data = json.load(file)
    except FileNotFoundError:
        arcade_data = []

    # 检查是否已有同名的 primary_keyword 在同一地区
    if any(arcade['primary_keyword'] == primary_keyword and arcade['region'] == region for arcade in arcade_data):
        await add_arcade_handler.send(f"机厅：{primary_keyword}\n地区：{region}\n已存在！")
        return

    # 添加新机厅并保存到文件
    current_arcade_data.append(new_arcade)
    with open(ARCADE_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(current_arcade_data, file, ensure_ascii=False, indent=2)

    # 即时更新地区数据
    sync_arcade_data()
    await add_arcade_handler.send(f"成功添加\n机厅：{primary_keyword}\n地区：{region}")

    
    
# 命令：删除机厅
delete_arcade_handler = on_command("删除机厅", priority=10, block=True)

@delete_arcade_handler.handle()
async def handle_delete_arcade(bot: Bot, event: GroupMessageEvent):
    message = event.get_message().extract_plain_text().strip()
    
    # 提取 primary_keyword 和 region
    args = message.replace("删除机厅", "").strip().split()
    if len(args) < 2:
        await delete_arcade_handler.send("格式错误：\n删除机厅<名称><地区>")
        return
    
    primary_keyword = args[0]
    region = args[1]
    
    # 读取 JSON 文件
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            arcade_data = json.load(file)
    except FileNotFoundError:
        arcade_data = []
    
    # 查找并删除指定地区和 primary_keyword 的机厅
    updated_arcade_data = [arcade for arcade in arcade_data if not (arcade["primary_keyword"] == primary_keyword and arcade["region"] == region)]

    if len(updated_arcade_data) == len(arcade_data):
        await delete_arcade_handler.send(f"未找到\n机厅：{primary_keyword}\n地区：{region}")
        return

    # 写回更新后的数据
    with open(ARCADE_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(updated_arcade_data, file, ensure_ascii=False, indent=2)

    sync_arcade_data()
    await delete_arcade_handler.send(f"成功删除\n机厅：{primary_keyword}\n地区：{region}")

    
# 命令：添加简称
add_keywords_handler = on_command("添加简称", priority=10, block=True)

@add_keywords_handler.handle()
async def handle_add_keywords(bot: Bot, event: GroupMessageEvent):
    message = event.get_message().extract_plain_text().strip()
    
    # 提取 primary_keyword, region 和 keywords
    args = message.replace("添加简称", "").strip().split()
    if len(args) < 3:
        await add_keywords_handler.send("格式错误：\n添加简称<名称><地区><简称>")
        return
    
    primary_keyword = args[0]
    region = args[1]
    keywords = args[2:]

    # 读取 JSON 文件
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            arcade_data = json.load(file)
    except FileNotFoundError:
        arcade_data = []

    # 查找指定的机厅并添加关键词
    for arcade in arcade_data:
        if arcade["primary_keyword"] == primary_keyword and arcade["region"] == region:
            arcade["keywords"] = list(set(arcade["keywords"] + keywords))
            break
    else:
        await add_keywords_handler.send(f"未找到\n机厅：{primary_keyword}\n地区：{region}")
        return

    # 写回更新后的数据
    with open(ARCADE_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(arcade_data, file, ensure_ascii=False, indent=2)

    sync_arcade_data()
    await add_keywords_handler.send(f"成功为\n机厅：{primary_keyword}\n地区：{region}\n添加简称：{'、'.join(keywords)}")

    
# 命令：删除简称
delete_keywords_handler = on_command("删除简称", priority=10, block=True)

@delete_keywords_handler.handle()
async def handle_delete_keywords(bot: Bot, event: GroupMessageEvent):
    message = event.get_message().extract_plain_text().strip()
    
    # 提取 primary_keyword, region 和 keywords
    args = message.replace("删除简称", "").strip().split()
    if len(args) < 3:
        await delete_keywords_handler.send("格式错误：\n删除简称<名称><地区><简称>")
        return
    
    primary_keyword = args[0]
    region = args[1]
    keywords = args[2:]

    # 读取 JSON 文件
    try:
        with open(ARCADE_DATA_FILE, 'r', encoding='utf-8') as file:
            arcade_data = json.load(file)
    except FileNotFoundError:
        arcade_data = []

    # 查找指定的机厅并删除关键词
    for arcade in arcade_data:
        if arcade["primary_keyword"] == primary_keyword and arcade["region"] == region:
            arcade["keywords"] = [keyword for keyword in arcade["keywords"] if keyword not in keywords]
            break
    else:
        await delete_keywords_handler.send(f"未找到\n机厅：{primary_keyword}\n地区：{region}")
        return

    # 写回更新后的数据
    with open(ARCADE_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(arcade_data, file, ensure_ascii=False, indent=2)

    sync_arcade_data()
    await delete_keywords_handler.send(f"成功为\n机厅：{primary_keyword}\n地区：{region}\n删除简称：{'、'.join(keywords)}")

    
# 新增去哪里勤的命令处理器
go_arcade_handler = on_command("随个机厅", aliases={"勤哪","去哪勤","qn"}, priority=10, block=True)

@go_arcade_handler.handle()
async def handle_go_arcade(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    group_region = read_group_region()

    # 检查群组是否有绑定地区
    if str(group_id) not in group_region:
        await go_arcade_handler.send("请先绑定机厅地区")
        return
    
    region_name = group_region[str(group_id)]
    
    # 从 state.json 中读取机厅数据
    arcades = read_state()

    # 筛选出属于该地区的机厅
    region_arcades = [arcade for arcade in arcades if arcade['region'] == region_name]

    if not region_arcades:
        await go_arcade_handler.send(f"未找到地区 {region_name} 的机厅数据")
        return

    # 随机选择一个机厅
    selected_arcade = random.choice(region_arcades)

    # 格式化机厅信息并发送
    response_message = format_arcades_message([selected_arcade], region_name)
    await go_arcade_handler.send(response_message)
