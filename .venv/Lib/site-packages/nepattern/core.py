from __future__ import annotations

from copy import deepcopy
from enum import Enum, IntEnum
import re
from typing import TYPE_CHECKING, Any, Callable, Generic, Literal, TypeVar
from typing_extensions import Self, get_args, get_origin

from tarina import Empty, generic_isinstance
from tarina.lang import lang

from .exception import MatchFailed


class MatchMode(IntEnum):
    """参数表达式匹配模式"""

    VALUE_OPERATE = 4
    """传入值进行操作"""
    REGEX_CONVERT = 3
    """正则匹配并转换"""
    TYPE_CONVERT = 2
    """传入值直接转换"""
    REGEX_MATCH = 1
    """正则匹配"""
    KEEP = 0
    """保持传入值"""


class ResultFlag(str, Enum):
    """参数表达式验证结果标识符"""

    VALID = "valid"
    "验证通过"
    ERROR = "error"
    "验证失败"
    DEFAULT = "default"
    "默认值"


T = TypeVar("T")
TInput = TypeVar("TInput", covariant=True)
TOrigin = TypeVar("TOrigin")
TVOrigin = TypeVar("TVOrigin")
TDefault = TypeVar("TDefault")
TVRF = TypeVar("TVRF", bound=ResultFlag)
TMM = TypeVar("TMM", bound=MatchMode)


class ValidateResult(Generic[TVOrigin, TVRF]):
    """参数表达式验证结果"""

    def __init__(
        self,
        value: TVOrigin | type[Empty] = Empty,
        error: Exception | type[Empty] = Empty,
        flag: TVRF = ResultFlag.VALID,
    ):
        self._value = value
        self._error = error
        self.flag = flag

    __slots__ = ("_value", "_error", "flag")

    def value(self) -> TVOrigin:
        if self.flag == ResultFlag.ERROR or self._value == Empty:
            raise RuntimeError("cannot access value")
        return self._value  # type: ignore

    def error(self) -> Exception | None:
        if self.flag == ResultFlag.ERROR and self._error != Empty:
            assert isinstance(self._error, Exception)
            return self._error

    @property
    def success(self) -> bool:
        return self.flag == ResultFlag.VALID

    @property
    def failed(self) -> bool:
        return self.flag == ResultFlag.ERROR

    @property
    def or_default(self) -> bool:
        return self.flag == ResultFlag.DEFAULT

    def step(
        self, other: type[T] | Callable[[TVOrigin], T] | Any | BasePattern[T, TVOrigin, MatchMode]
    ) -> T | Self | ValidateResult[T, TVRF]:
        if other is bool:
            return self.success  # type: ignore
        if callable(other) and self.success:
            return other(self.value())  # type: ignore
        return other.validate(self.value()) if isinstance(other, BasePattern) else self  # type: ignore

    def __rshift__(
        self, other: type[T] | Callable[[TVOrigin], T] | Any
    ) -> T | Self | ValidateResult[T, TVRF]:
        return self.step(other)  # type: ignore

    def __bool__(self):
        return self.flag != ResultFlag.ERROR

    def __repr__(self):
        if self.flag == ResultFlag.VALID:
            return f"ValidateResult(value={self._value!r})"
        if self.flag == ResultFlag.ERROR:
            return f"ValidateResult(error={self._error!r})"
        return f"ValidateResult(default={self._value!r})"


def _keep_any(self: BasePattern[Any, Any, Literal[MatchMode.KEEP]], input_: Any) -> Any:
    return input_


def _keep_no_previous(self: BasePattern[Any, Any, Literal[MatchMode.KEEP]], input_: Any) -> Any:
    if not self.accept(input_):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    return input_


def _keep_previous(self: BasePattern[Any, Any, Literal[MatchMode.KEEP]], input_: Any) -> Any:
    if TYPE_CHECKING:
        assert self.previous
    if self.accept(input_):
        input_ = self.previous.match(input_)
    elif not self.accept(input_ := self.previous.match(input_)):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    return input_


def select_keep_match(self: BasePattern[Any, Any, Literal[MatchMode.KEEP]]):
    if self._accepts or self._pattern_accepts:
        return _keep_previous if self.previous else _keep_no_previous
    return _keep_any


def _regex_match_no_previous(self: BasePattern[str, str, Literal[MatchMode.REGEX_MATCH]], input_: Any) -> str:
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        return mat[0]
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_match_type(self: BasePattern[str, str, Literal[MatchMode.REGEX_MATCH]], input_: Any) -> str:
    if TYPE_CHECKING:
        assert self.previous
    if not isinstance(input_, str) and not isinstance(
        input_ := self.previous.match(input_), str
    ):  # pragma: no cover
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        return mat[0]
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_match_value(self: BasePattern[str, str, Literal[MatchMode.REGEX_MATCH]], input_: Any) -> str:
    if TYPE_CHECKING:
        assert self.previous
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    input_ = self.previous.match(input_)
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        return mat[0]
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def select_regex_match(self: BasePattern[Any, Any, Literal[MatchMode.REGEX_MATCH]]):
    if self.previous:
        if self.previous.mode == MatchMode.TYPE_CONVERT:
            return _regex_match_type
        return _regex_match_value
    return _regex_match_no_previous


def _regex_convert_no_previous_any(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_convert_no_previous_other(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if generic_isinstance(input_, self.origin):
        return input_  # type: ignore
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_convert_any_type(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not isinstance(input_, str) and not isinstance(input_ := self.previous.match(input_), str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_convert_any_value(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    input_ = self.previous.match(input_)
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_convert_value(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    input_ = self.previous.match(input_)
    if generic_isinstance(input_, self.origin):
        return input_  # type: ignore
    if not isinstance(input_, str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def _regex_convert_type(
    self: BasePattern[TOrigin, str | TOrigin, Literal[MatchMode.REGEX_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if generic_isinstance(input_, self.origin):
        return input_  # type: ignore
    if not isinstance(input_, str) and not isinstance(input_ := self.previous.match(input_), str):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if mat := (self.regex_pattern.match(input_) or self.regex_pattern.search(input_)):
        if (res := self.converter(self, mat)) is not None:
            return res
    raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected=self.alias))


def select_regex_convert(self: BasePattern[Any, Any, Literal[MatchMode.REGEX_CONVERT]]):
    if self.origin is Any or self.origin is str:
        if not self.previous:
            return _regex_convert_no_previous_any
        return (
            _regex_convert_any_value
            if self.previous.mode == MatchMode.VALUE_OPERATE
            else _regex_convert_any_type
        )
    if not self.previous:
        return _regex_convert_no_previous_other
    if self.previous.mode == MatchMode.VALUE_OPERATE:
        return _regex_convert_value
    return _regex_convert_type


def _type_convert_no_previous_no_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_no_previous_no_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_no_previous_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if not self.accept(input_):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_no_previous_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if not self.accept(input_):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_type_no_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if (res := self.converter(self, input_)) is None and (
        res := self.converter(self, self.previous.match(input_))
    ) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_type_no_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None and (
        res := self.converter(self, self.previous.match(input_))
    ) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_type_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not self.accept(input_) and not self.accept(input_ := self.previous.match(input_)):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if (res := self.converter(self, input_)) is None and (
        res := self.converter(self, self.previous.match(input_))
    ) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_type_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not self.accept(input_) and not self.accept(input_ := self.previous.match(input_)):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None and (
        res := self.converter(self, self.previous.match(input_))
    ) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_value_no_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    input_ = self.previous.match(input_)
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_value_no_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    input_ = self.previous.match(input_)
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_value_accepts_any(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if self.accept(input_):
        input_ = self.previous.match(input_)
    elif not self.accept(input_ := self.previous.match(input_)):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _type_convert_value_accepts_other(
    self: BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if self.accept(input_):
        input_ = self.previous.match(input_)
    elif not self.accept(input_ := self.previous.match(input_)):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if generic_isinstance(input_, self.origin):
        return input_
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def select_type_convert(self: BasePattern[Any, Any, Literal[MatchMode.TYPE_CONVERT]]):
    if self._accepts or self._pattern_accepts:
        if self.origin is Any:
            if not self.previous:
                return _type_convert_no_previous_accepts_any
            return _type_convert_value_accepts_any if self.previous else _type_convert_type_accepts_any
        if not self.previous:
            return _type_convert_no_previous_accepts_other
        return _type_convert_value_accepts_other if self.previous else _type_convert_type_accepts_other
    if self.origin is Any:
        if not self.previous:
            return _type_convert_no_previous_no_accepts_any
        return _type_convert_value_no_accepts_any if self.previous else _type_convert_type_no_accepts_any
    if not self.previous:
        return _type_convert_no_previous_no_accepts_other
    return _type_convert_value_no_accepts_other if self.previous else _type_convert_type_no_accepts_other


def _value_operate_no_previous(
    self: BasePattern[TOrigin, TOrigin, Literal[MatchMode.VALUE_OPERATE]], input_: Any
) -> TOrigin:
    if not generic_isinstance(input_, self.origin):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _value_operate_type(
    self: BasePattern[TOrigin, TOrigin, Literal[MatchMode.VALUE_OPERATE]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not generic_isinstance(input_, self.origin) and not generic_isinstance(
        input_ := self.previous.match(input_), self.origin
    ):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def _value_operate_value(
    self: BasePattern[TOrigin, TOrigin, Literal[MatchMode.VALUE_OPERATE]], input_: Any
) -> TOrigin:
    if TYPE_CHECKING:
        assert self.previous
    if not generic_isinstance(input_, self.origin):
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected=self.alias
            )
        )
    input_ = self.previous.match(input_)
    if (res := self.converter(self, input_)) is None:
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
        )
    return res  # type: ignore


def select_value_operate(self: BasePattern[Any, Any, Literal[MatchMode.VALUE_OPERATE]]):
    if self.previous:
        if self.previous.mode == MatchMode.TYPE_CONVERT:
            return _value_operate_type
        return _value_operate_value
    return _value_operate_no_previous


_MATCHES = {
    MatchMode.KEEP: select_keep_match,
    MatchMode.REGEX_MATCH: select_regex_match,
    MatchMode.REGEX_CONVERT: select_regex_convert,
    MatchMode.TYPE_CONVERT: select_type_convert,
    MatchMode.VALUE_OPERATE: select_value_operate,
}


class BasePattern(Generic[TOrigin, TInput, TMM]):
    """对参数类型值的包装"""

    __slots__ = (
        "regex_pattern",
        "pattern",
        "mode",
        "converter",
        "origin",
        "alias",
        "previous",
        "validators",
        "match",
        "accept",
        "_accepts",
        "_pattern_accepts",
        "_hash",
        "_repr",
    )

    def __new__(cls, *args, **kwargs):
        cls.__eq__ = cls.__calc_eq__
        return super().__new__(cls)

    def __init__(
        self,
        pattern: str | None = None,
        mode: TMM | None = None,
        origin: type[TOrigin] | None = None,
        converter: Callable[[BasePattern, Any], TOrigin | None] | None = None,
        alias: str | None = None,
        previous: BasePattern | None = None,
        accepts: Any = None,
        addition_accepts: BasePattern | None = None,
        validators: list[Callable[[TOrigin], bool]] | None = None,
    ):
        """
        初始化参数匹配表达式
        """
        if pattern is None:
            _origin = origin or Any
            self.mode = MatchMode(mode or MatchMode.KEEP)
            self.pattern = ""
            self.regex_pattern = re.compile("")
        else:
            if pattern.startswith("^") or pattern.endswith("$"):
                raise ValueError(
                    lang.require("nepattern", "pattern_head_or_tail_error").format(target=pattern)
                )
            self.pattern = pattern
            self.regex_pattern = re.compile(f"^{pattern}$")
            self.mode = MatchMode(mode or MatchMode.REGEX_MATCH)
            _origin = origin or str
        self.origin: type[TOrigin] = _origin  # type: ignore
        self.alias = alias
        self.previous = previous
        if TYPE_CHECKING:
            assert self.origin is not None
        if self.mode == MatchMode.TYPE_CONVERT:
            if not converter and (not origin or origin is Any):
                raise ValueError(origin)
            self.converter = converter or (lambda _, x: (get_origin(self.origin) or self.origin)(x))  # type: ignore
        elif self.mode == MatchMode.VALUE_OPERATE:
            if not converter:
                raise ValueError(converter)
            self.converter = converter
        else:
            self.converter = converter or (lambda _, x: eval(x[0]))
        self.validators = validators or []
        if accepts is Any or not accepts:
            _accepts = Any
            self._accepts = ()
        else:
            _accepts = get_args(accepts) or accepts
            self._accepts = get_args(accepts) or (accepts,)
        self._pattern_accepts = addition_accepts
        self._repr = self.__calc_repr__()
        self._hash = self.__calc_hash__()

        if not addition_accepts:
            self.accept = (lambda x: True) if _accepts is Any else (lambda _: generic_isinstance(_, _accepts))
        elif _accepts is Any:
            self.accept = lambda _: addition_accepts.validate(_).flag == "valid"
        else:
            self.accept = lambda _: (
                generic_isinstance(_, _accepts) or addition_accepts.validate(_).flag == "valid"
            )
        if not hasattr(self, "match"):
            self.match = _MATCHES[self.mode](self).__get__(self)  # type: ignore

    def refresh(self):  # pragma: no cover
        self._repr = self.__calc_repr__()
        self._hash = self.__calc_hash__()

    def __calc_hash__(self):
        return hash(
            (self._repr, self.origin, self.mode, self.alias, self.previous, self._accepts, self.pattern)
        )

    def __calc_repr__(self):
        if self.mode == MatchMode.KEEP:
            if self.alias:
                return self.alias
            return (
                "Any"
                if not self._accepts and not self._pattern_accepts
                else "|".join([x.__name__ for x in self._accepts] + [self._pattern_accepts.__repr__()])
            )

        if not self.alias:
            name = getattr(self.origin, "__name__", str(self.origin))
            if self.mode == MatchMode.REGEX_MATCH:
                text = self.pattern
            elif self.mode == MatchMode.REGEX_CONVERT or (not self._accepts and not self._pattern_accepts):
                text = name
            else:
                text = (
                    "|".join([x.__name__ for x in self._accepts] + [self._pattern_accepts.__repr__()])
                    + f" -> {name}"
                )
        else:
            text = self.alias
        return (
            f"{f'{self.previous.__repr__()} -> ' if self.previous and id(self.previous) != id(self) else ''}"
            f"{text}"
        )

    def __repr__(self):
        return self._repr

    def __str__(self):
        return self._repr

    def __hash__(self):
        return self._hash

    def __calc_eq__(self, other):
        return isinstance(other, self.__class__) and self._hash == other._hash

    @staticmethod
    def of(unit: type[TOrigin]):
        """提供 Type[DataUnit] 类型的构造方法"""
        from .base import DirectTypePattern

        return DirectTypePattern(unit)

    @staticmethod
    def on(obj: TOrigin):
        """提供 DataUnit 类型的构造方法"""
        from .base import DirectPattern

        return DirectPattern(obj)

    @staticmethod
    def to(content: Any):
        """便捷的使用 type_parser 的方法"""
        from .main import parser

        res = parser(content, "allow")
        return res if isinstance(res, BasePattern) else parser(Any)  # type: ignore

    def validate(self, input_: Any, default: TDefault | Empty = Empty) -> ValidateResult[TOrigin | TDefault, ResultFlag]:  # type: ignore
        """
        对传入的值进行正向验证，返回可能的匹配与转化结果。

        若传入默认值，验证失败会返回默认值
        """
        try:
            res = self.match(input_)
            if self.validators and not all(i(res) for i in self.validators):
                raise MatchFailed(lang.require("nepattern", "validate_error").format(target=input_))
            return ValidateResult(value=res, flag=ResultFlag.VALID)
        except Exception as e:
            if default is Empty:
                return ValidateResult(error=e, flag=ResultFlag.ERROR)
            return ValidateResult(default, flag=ResultFlag.DEFAULT)  # type: ignore

    def copy(self) -> Self:
        return deepcopy(self)

    def __rrshift__(self, other):
        return self.validate(other)

    def __rmatmul__(self, other) -> Self:  # pragma: no cover
        if isinstance(other, str):
            self.alias = other
        return self

    def __matmul__(self, other) -> Self:  # pragma: no cover
        if isinstance(other, str):
            self.alias = other
        return self

    def __or__(self, other):
        from .base import UnionPattern

        if isinstance(other, BasePattern):
            return UnionPattern([self, other])  # type: ignore
        raise TypeError(  # pragma: no cover
            f"unsupported operand type(s) for |: 'BasePattern' and '{other.__class__.__name__}'"
        )
