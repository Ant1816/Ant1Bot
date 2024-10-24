"""Alconna ArgAction相关"""

from datetime import datetime
from tarina import lang
from typing import Literal
from dataclasses import dataclass, field
from arclet.alconna.exceptions import OutBoundsBehave
from arclet.alconna.arparma import Arparma, ArparmaBehavior


def exclusion(target_path: str, other_path: str):
    """
    当设置的两个路径同时存在时, 抛出异常

    Args:
        target_path: 目标路径
        other_path: 其他路径
    """

    class _EXCLUSION(ArparmaBehavior):
        def operate(self, interface: "Arparma"):
            if interface.query(target_path) and interface.query(other_path):
                raise OutBoundsBehave(
                    lang.require("tools", "actions.exclusion").format(left=target_path, right=other_path)
                )

    return _EXCLUSION()


def cool_down(seconds: float):
    """
    当设置的时间间隔内被调用时, 抛出异常

    Args:
        seconds: 时间间隔
    """

    @dataclass(unsafe_hash=True)
    class _CoolDown(ArparmaBehavior):
        last_time: datetime = field(default_factory=lambda: datetime.now())

        def operate(self, interface: "Arparma"):
            current_time = datetime.now()
            if (current_time - self.last_time).total_seconds() < seconds:
                raise OutBoundsBehave(lang.require("tools", "actions.cooldown"))
            else:
                self.last_time = current_time

    return _CoolDown()


def inclusion(*targets: str, flag: Literal["any", "all"] = "any"):
    """
    当设置的路径不存在时, 抛出异常

    Args:
        targets: 路径列表
        flag: 匹配方式, 可选值为"any"或"all", 默认为"any"
    """

    class _Inclusion(ArparmaBehavior):
        def operate(self, interface: "Arparma"):
            if flag == "all":
                for target in targets:
                    if not interface.query(target):
                        raise OutBoundsBehave(lang.require("tools", "actions.inclusion").format(target=target))
            else:
                all_count = len(targets) - sum(1 for target in targets if interface.query(target))
                if all_count > 0:
                    raise OutBoundsBehave(lang.require("tools", "actions.inclusion"))
    return _Inclusion()
