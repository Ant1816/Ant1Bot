from __future__ import annotations

import re
from collections.abc import Awaitable, Generator, Iterable
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeVar, overload

from typing_extensions import Concatenate, ParamSpec

from .guard import is_async

T = TypeVar("T")


def group_dict(iterable: Iterable, key_callable: Callable[[Any], Any]):
    temp = {}
    for i in iterable:
        k = key_callable(i)
        temp.setdefault(k, []).append(i)
    return temp


async def run_always_await(target: Callable[..., Any] | Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
    obj = target(*args, **kwargs)
    if is_async(target) or is_async(obj):
        obj = await obj  # type: ignore
    return obj


def gen_subclass(cls: type[T]) -> Generator[type[T], None, None]:
    """生成某个类的所有子类 (包括其自身)
    Args:
        cls (Type[T]): 类
    Yields:
        Type[T]: 子类
    """
    yield cls
    for sub_cls in cls.__subclasses__():
        if TYPE_CHECKING:
            assert issubclass(sub_cls, cls)
        yield from gen_subclass(sub_cls)


R = TypeVar("R")
P = ParamSpec("P")
C = TypeVar("C")


@overload
def init_spec(fn: Callable[P, T]) -> Callable[[Callable[[T], R]], Callable[P, R]]: ...


@overload
def init_spec(
    fn: Callable[P, T], is_method: Literal[True]
) -> Callable[[Callable[[C, T], R]], Callable[Concatenate[C, P], R]]: ...


def init_spec(  # type: ignore
    fn: Callable[P, T], is_method: bool = False
) -> Callable[[Callable[[T], R] | Callable[[C, T], R]], Callable[P, R] | Callable[Concatenate[C, P], R]]:
    def wrapper(func: Callable[[T], R] | Callable[[C, T], R]) -> Callable[P, R] | Callable[Concatenate[C, P], R]:
        def inner(*args: P.args, **kwargs: P.kwargs):
            if is_method:
                return func(args[0], fn(*args[1:], **kwargs))  # type: ignore
            return func(fn(*args, **kwargs))  # type: ignore

        return inner

    return wrapper


def safe_eval(route: str, _locals: dict[str, Any]):
    parts = re.split(r"\.|(\[.+?\])|(\(.*?\))", route)
    if (key := parts[0]) not in _locals:
        raise NameError(key)
    res = _locals[key]
    for part in parts[1:]:
        if not part:
            continue
        if part.startswith("_"):
            raise ValueError(route)
        if part.startswith("[") and part.endswith("]"):
            item = part[1:-1]
            if item[0] in ("'", '"') and item[-1] in ("'", '"'):
                res = res[item[1:-1]]
            elif ":" in item:
                res = res[slice(*(int(x) if x else None for x in item.split(":")))]
            else:
                try:
                    res = res[int(item)]
                except ValueError:
                    res = res[item]
        elif part.startswith("(") and part.endswith(")"):
            item = part[1:-1]
            if not item:
                res = res()
            else:
                _parts = item.split(",")
                _args = []
                _kwargs = {}
                for _part in _parts:
                    _part = _part.strip()
                    if re.match(".+=.+", _part):
                        k, v = _part.split("=")
                        if v[0] in ("'", '"') and v[-1] in ("'", '"'):
                            v = v[1:-1]
                        _kwargs[k] = v
                    else:
                        if _part[0] in ("'", '"') and _part[-1] in ("'", '"'):
                            _part = _part[1:-1]
                        _args.append(_part)
                res = res(*_args, **_kwargs)
        else:
            res = getattr(res, part)
    return res


def uncapitalize(source: str) -> str:
    return source[0].lower() + source[1:]


def camel_case(source: str) -> str:
    return re.sub("[_-][a-z]", lambda mat: mat[0][1:].upper(), source)


def pascal_case(source: str) -> str:
    return re.sub("[_-][a-z]", lambda mat: mat[0][1:].upper(), source.capitalize())


def param_case(source: str) -> str:
    return re.sub(".[A-Z]+", lambda mat: mat[0][0] + "-" + mat[0][1:].lower(), uncapitalize(source).replace("_", "-"))


def snake_case(source: str) -> str:
    return re.sub(".[A-Z]", lambda mat: mat[0][0] + "_" + mat[0][1:].lower(), uncapitalize(source).replace("-", "_"))
