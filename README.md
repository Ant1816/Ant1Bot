<div align=center>

<img src="https://github.com/Ant1816/Ant1816/blob/main/avatar.png" width = "200" height = "200" />

</div>

<div align=center>

# 小安提Bot

</div>

<div align=center>

**基于 [NoneBot2](https://github.com/nonebot/nonebot2) 服务于音游 `舞萌DX` 的QQbot**

</div>

<div align=center>

[![Python3.12.4](https://img.shields.io/badge/Python-3.12.4-blue)](https://www.python.org/downloads/release/python-3124/)
[![pipx](https://img.shields.io/badge/pipx-1.7.1-yellow)](https://pipx.pypa.io/stable/)
[![OneBot](https://img.shields.io/badge/OneBot-v11-brown)](https://github.com/botuniverse/onebot-11)
[![NoneBot2](https://img.shields.io/badge/NoneBot-2.0-red)](https://github.com/nonebot/nonebot2)

</div>

**请提前点击上方Python图标或自行下载安装Python3.12.4**

**部署bot后请自行修改Bot配置文件 `.env` 和Python虚拟环境配置文件 `.venv\pyvenv.cfg` 以及部署NoneBot2环境（相关问题可以查看NoneBot帮助文档）**

**缺少的配置参数可以给bot发送 `获取插件列表` 获得插件名字后自行查找参数**

## 此帮助文档不提供任何和QQ对接的指引

***

<div align=center>

# 它能干什么

</div>

<div align=center>

## maimaiDX相关功能

</div>

| 命令                                             | 功能                            |
|------------------------------------------------|-------------------------------|
| 帮助maimaiDX                                     | 查看指令帮助                        |
| 今日舞萌                                           | 查看今天的舞萌运势                     |
| XXXmaimaiXXX什么                                 | 随机一首歌                         |
| 随个[dx/标准][绿黄红紫白]<难度>                           | 随机一首指定条件的乐曲                   |
| 查歌<乐曲标题的一部分>                                   | 查询符合条件的乐曲                     |
| id<歌曲编号>                                | 查询乐曲信息或谱面信息                   |
| <歌曲别名>是什么歌                                     | 查询乐曲别名对应的乐曲                   |
| <id/歌曲别称>有什么别称                                 | 查询歌曲别名                        |
| 添加本地别名 <歌曲ID> <歌曲别名>                         | 添加本地别名，不上传别名服务器         |
| 添加别称 <歌曲ID> <歌曲别名>                             | 申请添加歌曲别名                      |
| 当前别名投票 <页数>                                        | 查看正在进行的投票                     |
| 同意别名 <标签>                                      | 同意其中一个标签的别名申请，可通过指令 当前别名投票 查看 |
| 开启/关闭别名推送                                      | 开启或关闭新别名投票的推送                 |
| 定数查歌 <定数> 定数查歌 <定数下限> <定数上限>                   | 查询定数对应的乐曲                     |
| 分数线 <难度+歌曲id> <分数线>                            | 展示歌曲的分数线                      |
| 开启/关闭mai猜歌                                     | 开关猜歌功能                        |
| 重置猜歌                                            | 停止当前进行的猜歌                  |
| 猜歌                                             | 顾名思义，识别id，歌名和别称               |
| 猜曲绘                                            | 猜曲绘                                |
| minfo<@> <id/别称/曲名>                            | 查询单曲成绩                        |
| ginfo[绿黄红紫白] <id/别称/曲名>                        | 查询乐曲游玩总览，不加难度默认为紫谱         |
| b50 <游戏名>                                      | 查询b50                         |
| 我要在<难度>上<分数>分 <游戏名>                            | 查看推荐的上分乐曲                     |
| 我要(在<难度>)上<分数>分 <名字>                           | 查看推荐的上分乐曲                     |
| <牌子名称>进度 <名字>                                  | 查看牌子完成进度                      |
| <等级><评价>进度 <名字>                                | 查看等级评价完成进度                    |
| <等级> 分数列表 <名字>                                 | 查看等级评价列表                      |
| 查看排名,查看排行 <页数>/<名字>                            | 查看水鱼网站的用户ra排行                 |
| 添加机厅 <店名> <位置> <机台数量>                     | 添加机厅信息                        |
| 删除机厅 <店名>                                      | 删除机厅信息                        |
| 修改机厅 <店名> 数量 <数量>                           | 修改机厅信息                        |
| 订阅机厅 <店名>                                      | 订阅机厅，简化后续指令                   |
| 查看订阅                                           | 查看群组订阅机厅的信息                   |
| 取消订阅,取消订阅机厅                                    | 取消群组机厅订阅                      |
| 添加机厅别名 <店名> <别名>                                | 添加机厅别名                      |
| 查找机厅,查询机厅,机厅查找,机厅查询 <关键词>                      | 查询对应机厅信息                      |
| <店名/别名>人数设置,设定,增加,加,+,减少,减,-<人数>                  | 操作排卡人数                        |
| <店名/别名>有多少人,有几人,有几卡,几人,几卡                         | 查看排卡人数                        |
| 全局[关闭/开启]别名推送                               | Bot管理员私聊指令，开关所有群的别名推送   |
| 更新别名库                                            | Bot管理员私聊指令，手动更新别名库   |
| 更新maimai数据                                            | Bot管理员私聊指令，手动更新已存所有数据  |

### 另有多个实用插件预装（兼容NoneBot插件 列表更新可能不及时 请自行 `获取插件列表`）
- `ProjectSekai表情包生成`
- `本地机厅管理`
- `戳一戳获取服务器状态`
- `树形插件帮助`
- `涩图`
- `漫展信息查询`
- `群管理`
- `猜单词`
- `便捷插件管理`
## 更多功能等你探索哦！
***
## License
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)