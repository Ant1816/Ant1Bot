from functools import wraps
from typing import Callable, Optional, TypeVar

from arclet.alconna import Alconna, CommandMeta, Args
from typing_extensions import ParamSpec

T = TypeVar("T")
P = ParamSpec("P")


def simple_type(raise_exception: bool = False):
    def deco(func: Callable[P, T]) -> Callable[P, Optional[T]]:
        name: str = f"{id(func)}"
        _cmd = Alconna(
            name, Args.from_callable(func)[0],
            meta=CommandMeta(raise_exception=raise_exception)
        )

        @wraps(func)
        def __wrapper__(*args: P.args, **kwargs: P.kwargs):
            param = [name, *args]
            for k, v in kwargs.items():
                param.extend([f"{k}=", v])
            res = _cmd.parse(param)
            return res.call(func) if res.matched else None

        return __wrapper__

    return deco
