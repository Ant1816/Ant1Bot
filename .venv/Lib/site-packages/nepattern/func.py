from __future__ import annotations

from functools import reduce
from typing import Any, Callable, Protocol, TypeVar, overload

from tarina import Empty

from .core import TMM, BasePattern, MatchMode, TInput

T = TypeVar("T")
T1 = TypeVar("T1")


def Index(
    pat: BasePattern[list[T], TInput, TMM],
    index: int,
) -> BasePattern[T, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return _match(input_)[index]

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}[{index}]"
    _new.refresh()
    return _new  # type: ignore


def Slice(
    pat: BasePattern[list[T], TInput, TMM],
    start: int | None = None,
    end: int | None = None,
    step: int = 1,
) -> BasePattern[list[T], TInput, TMM]:
    if start is None and end is None:
        return pat
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return _match(input_)[start:end:step]

    _new.match = match.__get__(_new)
    if start is not None and end is not None:
        _slice = f"{start}:{end}"
    elif start is not None:
        _slice = f"{start}:"
    else:
        _slice = f":{end}"
    if step != 1:
        _slice += f":{step}"
    _new.alias = f"{_new._repr}[{_slice}]"
    _new.refresh()
    return _new


def Map(
    pat: BasePattern[list[T], TInput, TMM],
    func: Callable[[T], T1],
    funcname: str | None = None,
) -> BasePattern[list[T1], TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return list(map(func, _match(input_)))

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.map({funcname or func.__name__})"
    _new.refresh()
    return _new  # type: ignore


def Filter(
    pat: BasePattern[list[T], TInput, TMM],
    func: Callable[[T], bool],
    funcname: str | None = None,
) -> BasePattern[list[T], TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return list(filter(func, _match(input_)))

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.filter({funcname or func.__name__})"
    _new.refresh()
    return _new


_T_contra = TypeVar("_T_contra", contravariant=True)
_T_co = TypeVar("_T_co", covariant=True)


class SupportsAdd(Protocol[_T_contra, _T_co]):
    def __add__(self, x: _T_contra, /) -> _T_co: ...


class SupportsRAdd(Protocol[_T_contra, _T_co]):
    def __radd__(self, x: _T_contra, /) -> _T_co: ...


class _SupportsSumWithNoDefaultGiven(SupportsAdd[Any, Any], SupportsRAdd[int, Any], Protocol): ...


_SupportsSumNoDefaultT = TypeVar("_SupportsSumNoDefaultT", bound=_SupportsSumWithNoDefaultGiven)


def Sum(
    pat: BasePattern[list[_SupportsSumNoDefaultT], TInput, TMM]
) -> BasePattern[_SupportsSumNoDefaultT, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return sum(_match(input_))

    _new.match = match.__get__(_new)
    _new.alias = f"sum({_new._repr})"
    _new.refresh()
    return _new  # type: ignore


@overload
def Reduce(
    pat: BasePattern[list[T], TInput, TMM],
    func: Callable[[T, T], T],
    initializer: None = ...,
    funcname: str | None = ...,
) -> BasePattern[T, TInput, TMM]: ...


@overload
def Reduce(
    pat: BasePattern[list[T], TInput, TMM],
    func: Callable[[T1, T], T1],
    initializer: T1,
    funcname: str | None = ...,
) -> BasePattern[T1, TInput, TMM]: ...


def Reduce(
    pat: BasePattern[list[T], TInput, TMM],
    func: Callable[[T, T], T] | Callable[[T1, T], T1],
    initializer: T1 | None = None,
    funcname: str | None = None,
) -> BasePattern[T, TInput, TMM] | BasePattern[T1, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return reduce(func, _match(input_), initializer) if initializer is not None else reduce(func, _match(input_))  # type: ignore

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.reduce({funcname or func.__name__})"
    _new.refresh()
    return _new  # type: ignore


def Join(
    pat: BasePattern[list[str], TInput, TMM],
    sep: str,
) -> BasePattern[str, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return sep.join(_match(input_))

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.join({sep!r})"
    _new.refresh()
    return _new  # type: ignore


def Upper(
    pat: BasePattern[str, TInput, TMM],
) -> BasePattern[str, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return _match(input_).upper()

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.upper()"
    _new.refresh()
    return _new  # type: ignore


def Lower(
    pat: BasePattern[str, TInput, TMM],
) -> BasePattern[str, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return _match(input_).lower()

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.lower()"
    _new.refresh()
    return _new  # type: ignore


def Dot(
    pat: BasePattern[Any, TInput, TMM],
    origin: type[T],
    key: str,
    default: T | None = None,
) -> BasePattern[T, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return getattr(_match(input_), key, default)

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.{key}"
    _new.refresh()
    _new.origin = origin
    return _new  # type: ignore


def GetItem(
    pat: BasePattern[Any, TInput, TMM],
    origin: type[T],
    key: str,
    default: T | None = None,
) -> BasePattern[T, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_) -> T:
        try:
            return _match(input_)[key]
        except Exception as e:
            if default is not None:
                return default
            raise e

    _new.match = match.__get__(_new)
    _new.alias = f"{_new._repr}.{key}"
    _new.refresh()
    _new.origin = origin
    return _new  # type: ignore


def Step(
    pat: BasePattern[T, TInput, TMM],
    func: Callable[[T], T1],
    *args,
    funcname: str | None = None,
    **kwargs,
) -> BasePattern[T1, TInput, TMM]:
    _new = pat.copy()
    _match = _new.match

    def match(self, input_):
        return func(_match(input_), *args, **kwargs)

    _new.match = match.__get__(_new)
    _new.alias = f"{funcname or func.__name__}({_new._repr})"
    _new.refresh()
    return _new  # type: ignore
