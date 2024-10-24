from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
import re
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    ForwardRef,
    Generic,
    Iterable,
    Literal,
    Match,
    TypeVar,
    Union,
    cast,
    final,
    overload,
)

from tarina import DateParser, Empty, lang

from .core import _MATCHES, TMM, BasePattern, MatchMode, ResultFlag, ValidateResult
from .exception import MatchFailed
from .util import TPattern

TOrigin = TypeVar("TOrigin")
TDefault = TypeVar("TDefault")
_T = TypeVar("_T")
_T1 = TypeVar("_T1")


class DirectPattern(BasePattern[TOrigin, TOrigin, Literal[MatchMode.KEEP]]):
    """直接判断"""

    def __init__(self, target: TOrigin, alias: str | None = None):
        self.target = target
        super().__init__(mode=MatchMode.KEEP, origin=type(target), alias=alias or str(target))

    def match(self, input_: Any):
        if input_ != self.target:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected=self.target)
            )
        return input_

    @overload
    def validate(self, input_: TOrigin) -> ValidateResult[TOrigin, Literal[ResultFlag.VALID]]: ...

    @overload
    def validate(self, input_: _T) -> ValidateResult[_T, Literal[ResultFlag.ERROR]]: ...

    @overload
    def validate(
        self, input_: TOrigin, default: Any
    ) -> ValidateResult[TOrigin, Literal[ResultFlag.VALID]]: ...

    @overload
    def validate(
        self, input_: Any, default: TDefault
    ) -> ValidateResult[TDefault, Literal[ResultFlag.DEFAULT]]: ...

    def validate(self, input_: Any, default: Union[TDefault, Empty] = Empty) -> ValidateResult[TOrigin | TDefault, ResultFlag]:  # type: ignore
        try:
            return ValidateResult(self.match(input_), flag=ResultFlag.VALID)
        except MatchFailed as e:
            if default is Empty:
                return ValidateResult(error=e, flag=ResultFlag.ERROR)
            return ValidateResult(default, flag=ResultFlag.DEFAULT)  # type: ignore

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, DirectPattern) and self.target == other.target

    def copy(self):
        return DirectPattern(self.target, self.alias)


class DirectTypePattern(BasePattern[TOrigin, TOrigin, Literal[MatchMode.KEEP]]):
    """直接类型判断"""

    def __init__(self, target: type[TOrigin], alias: str | None = None):
        self.target = target
        super().__init__(mode=MatchMode.KEEP, origin=target, alias=alias or target.__name__)

    def match(self, input_: Any):
        if not isinstance(input_, self.target):
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected=self.target
                )
            )
        return input_

    @overload
    def validate(self, input_: TOrigin) -> ValidateResult[TOrigin, Literal[ResultFlag.VALID]]: ...

    @overload
    def validate(self, input_: _T) -> ValidateResult[_T, Literal[ResultFlag.ERROR]]: ...

    @overload
    def validate(
        self, input_: TOrigin, default: Any
    ) -> ValidateResult[TOrigin, Literal[ResultFlag.VALID]]: ...

    @overload
    def validate(
        self, input_: Any, default: TDefault
    ) -> ValidateResult[TDefault, Literal[ResultFlag.DEFAULT]]: ...

    def validate(self, input_: Any, default: Union[TDefault, Empty] = Empty) -> ValidateResult[TOrigin | TDefault, ResultFlag]:  # type: ignore
        try:
            return ValidateResult(self.match(input_), flag=ResultFlag.VALID)
        except MatchFailed as e:
            if default is Empty:
                return ValidateResult(error=e, flag=ResultFlag.ERROR)
            return ValidateResult(default, flag=ResultFlag.DEFAULT)  # type: ignore

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, DirectTypePattern) and self.target == other.target

    def copy(self):
        return DirectTypePattern(self.target, self.alias)


class RegexPattern(BasePattern[Match[str], str, Literal[MatchMode.REGEX_MATCH]]):
    """针对正则的特化匹配，支持正则组"""

    def __init__(self, pattern: str | TPattern, alias: str | None = None):
        super().__init__("", origin=Match[str], alias=alias or "regex[:group]")  # type: ignore
        self.regex_pattern = re.compile(pattern)
        self.pattern = self.regex_pattern.pattern

    def match(self, input_: Any) -> Match[str]:
        if not isinstance(input_, str):
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected="str"
                )
            )
        if mat := self.regex_pattern.match(input_):
            return mat
        raise MatchFailed(
            lang.require("nepattern", "content_error").format(target=input_, expected=self.pattern)
        )

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, RegexPattern) and self.pattern == other.pattern

    def copy(self):
        return RegexPattern(self.pattern, self.alias)


class UnionPattern(BasePattern[Any, _T, Literal[MatchMode.KEEP]]):
    """多类型参数的匹配"""

    optional: bool
    for_validate: list[BasePattern]
    for_equal: list[str | object]

    __slots__ = ("base", "optional", "for_validate", "for_equal")

    def __init__(self, base: Iterable[BasePattern[Any, _T, Any] | _T]):
        self.base = list(base)
        self.optional = False
        self.for_validate = []
        self.for_equal = []

        for arg in self.base:
            if arg == NONE:
                self.optional = True
                self.for_equal.append(None)
            elif isinstance(arg, BasePattern):
                self.for_validate.append(arg)
            else:
                self.for_equal.append(arg)
        alias_content = "|".join([repr(a) for a in self.for_validate] + [repr(a) for a in self.for_equal])
        super().__init__(mode=MatchMode.KEEP, origin=Any, alias=alias_content)

    def match(self, input_: Any):
        if not input_:
            input_ = None
        if input_ not in self.for_equal:
            for pat in self.for_validate:
                if (res := pat.validate(input_)).success:
                    return res.value()
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected=self.alias)
            )
        return input_

    @classmethod
    def _(cls, *types: type[_T1]) -> UnionPattern[_T1]:
        from .main import parser

        return cls([parser(i) for i in types])  # type: ignore

    def __calc_repr__(self):
        return "|".join(repr(a) for a in (*self.for_validate, *self.for_equal))

    def __or__(self, other: BasePattern[Any, _T1, Any]) -> UnionPattern[Union[_T, _T1]]:
        return UnionPattern([*self.base, other])  # type: ignore

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, UnionPattern) and self.base == other.base


TSeq = TypeVar("TSeq", list, tuple, set)


class IterMode(str, Enum):
    PRE = "pre"
    SUF = "suf"
    ALL = "all"


TIterMode = TypeVar("TIterMode", bound=IterMode)


class SequencePattern(
    BasePattern[TSeq, Union[str, TSeq], Literal[MatchMode.REGEX_CONVERT]], Generic[TSeq, TIterMode]
):
    """匹配列表或者元组或者集合"""

    base: BasePattern
    itermode: TIterMode

    def __init__(self, form: type[TSeq], base: BasePattern, mode: TIterMode = IterMode.ALL):
        self.base = base
        self.itermode = mode
        if form is list:
            super().__init__(r"\[(.+?)\]", MatchMode.REGEX_CONVERT, form, alias=f"list[{base}]")
        elif form is tuple:
            super().__init__(r"\((.+?)\)", MatchMode.REGEX_CONVERT, form, alias=f"tuple[{base}]")
        elif form is set:
            super().__init__(r"\{(.+?)\}", MatchMode.REGEX_CONVERT, form, alias=f"set[{base}]")
        else:
            raise ValueError(lang.require("nepattern", "sequence_form_error").format(target=str(form)))
        self.converter = lambda _, x: x[1]  # type: ignore
        self._match = _MATCHES[MatchMode.REGEX_CONVERT](self)

    def match(self, input_: Any):
        _res = self._match(self, input_)  # type: ignore
        _max = 0
        success: list[tuple[int, Any]] = []
        fail: list[tuple[int, MatchFailed]] = []
        for _max, s in enumerate(re.split(r"\s*,\s*", _res) if isinstance(_res, str) else _res):
            try:
                success.append((_max, self.base.match(s)))
            except MatchFailed:
                fail.append((_max, MatchFailed(f"{s} is not matched with {self.base}")))

        if (
            (self.itermode == IterMode.ALL and fail)
            or (self.itermode == IterMode.PRE and fail and fail[0][0] == 0)
            or (self.itermode == IterMode.SUF and fail and fail[-1][0] == _max)
        ):
            raise fail[0][1]
        if self.itermode == IterMode.PRE and fail:
            return self.origin(i[1] for i in success if i[0] < fail[0][0])
        if self.itermode == IterMode.SUF and fail:
            return self.origin(i[1] for i in success if i[0] > fail[-1][0])
        return self.origin(i[1] for i in success)

    def __calc_repr__(self):
        return f"{self.origin.__name__}[{self.base}]"


TKey = TypeVar("TKey")
TVal = TypeVar("TVal")


class MappingPattern(
    BasePattern[Dict[TKey, TVal], Union[str, Dict[TKey, TVal]], Literal[MatchMode.REGEX_CONVERT]],
    Generic[TKey, TVal, TIterMode],
):
    """匹配字典或者映射表"""

    key: BasePattern[TKey, Any, Any]
    value: BasePattern[TVal, Any, Any]
    itermode: TIterMode

    def __init__(
        self,
        arg_key: BasePattern[TKey, Any, Any],
        arg_value: BasePattern[TVal, Any, Any],
        mode: TIterMode = IterMode.ALL,
    ):
        self.key = arg_key
        self.value = arg_value
        self.itermode = mode
        super().__init__(
            r"\{(.+?)\}",
            MatchMode.REGEX_CONVERT,
            dict,
            alias=f"dict[{self.key}, {self.value}]",
        )
        self.converter = lambda _, x: x[1]
        self._match = _MATCHES[MatchMode.REGEX_CONVERT](self)

    def match(self, input_: str | dict):
        _res = self._match(self, input_)  # type: ignore
        success: list[tuple[int, Any, Any]] = []
        fail: list[tuple[int, MatchFailed]] = []
        _max = 0

        def _generator_items(res: str | dict):
            if isinstance(res, dict):
                yield from res.items()
                return
            for m in re.split(r"\s*,\s*", res):
                yield re.split(r"\s*[:=]\s*", m)

        for _max, item in enumerate(_generator_items(_res)):
            k, v = item
            try:
                success.append((_max, self.key.match(k), self.value.match(v)))
            except MatchFailed:
                fail.append(
                    (
                        _max,
                        MatchFailed(f"{k}: {v} is not matched with {self.key}: {self.value}"),
                    )
                )
        if (
            (self.itermode == IterMode.ALL and fail)
            or (self.itermode == IterMode.PRE and fail and fail[0][0] == 0)
            or (self.itermode == IterMode.SUF and fail and fail[-1][0] == _max)
        ):
            raise fail[0][1]
        if self.itermode == IterMode.PRE and fail:
            return {i[1]: i[2] for i in success if i[0] < fail[0][0]}
        if self.itermode == IterMode.SUF and fail:
            return {i[1]: i[2] for i in success if i[0] > fail[-1][0]}
        return {i[1]: i[2] for i in success}

    def __calc_repr__(self):
        return f"dict[{self.key.origin.__name__}, {self.value}]"


_TCase = TypeVar("_TCase")
_TSwtich = TypeVar("_TSwtich")


class SwitchPattern(BasePattern[_TCase, _TSwtich, Literal[MatchMode.TYPE_CONVERT]], Generic[_TCase, _TSwtich]):
    """匹配多种情况的表达式"""
    switch: dict[_TSwtich | ellipsis, _TCase]

    __slots__ = ("switch",)

    def __init__(self, data: dict[_TSwtich, _TCase] | dict[_TSwtich | ellipsis, _TCase]):
        self.switch = data  # type: ignore
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=type(list(data.values())[0]))

    def __calc_repr__(self):
        return "|".join(f"{k}" for k in self.switch if k != Ellipsis)

    def match(self, input_: Any) -> _TCase:
        try:
            return self.switch[input_]
        except KeyError as e:
            if Ellipsis in self.switch:
                return self.switch[...]
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected=self._repr)
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, SwitchPattern) and self.switch == other.switch


class ForwardRefPattern(BasePattern[Any, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self, ref: ForwardRef):
        self.ref = ref
        super().__init__(
            mode=MatchMode.TYPE_CONVERT, origin=Any, converter=lambda _, x: eval(x), alias=ref.__forward_arg__
        )

    def match(self, input_: Any):
        if isinstance(input_, str) and input_ == self.ref.__forward_arg__:
            return input_
        _main = sys.modules["__main__"]
        if sys.version_info < (3, 9):  # pragma: no cover
            origin = self.ref._evaluate(_main.__dict__, _main.__dict__)
        else:  # pragma: no cover
            origin = self.ref._evaluate(_main.__dict__, _main.__dict__, recursive_guard=frozenset())  # type: ignore
        if not isinstance(input_, origin):  # type: ignore
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected=self.ref.__forward_arg__
                )
            )
        return input_

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, ForwardRefPattern) and self.ref == other.ref


class AntiPattern(BasePattern[TOrigin, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self, pattern: BasePattern[TOrigin, Any, Any]):
        self.base: BasePattern[TOrigin, Any, Any] = pattern
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=pattern.origin, alias=f"!{pattern}")

    @overload
    def validate(self, input_: TOrigin) -> ValidateResult[Any, Literal[ResultFlag.ERROR]]: ...

    @overload
    def validate(self, input_: _T) -> ValidateResult[_T, Literal[ResultFlag.VALID]]: ...

    @overload
    def validate(
        self, input_: TOrigin, default: TDefault
    ) -> ValidateResult[TDefault, Literal[ResultFlag.DEFAULT]]: ...

    @overload
    def validate(self, input_: _T, default: Any) -> ValidateResult[_T, Literal[ResultFlag.VALID]]: ...

    def validate(self, input_: _T, default: Union[TDefault, Empty] = Empty) -> ValidateResult[_T | TDefault, ResultFlag]:  # type: ignore
        """
        对传入的值进行反向验证，返回可能的匹配与转化结果。

        若传入默认值，验证失败会返回默认值
        """
        try:
            res = self.base.match(input_)
        except MatchFailed:
            return ValidateResult(value=input_, flag=ResultFlag.VALID)
        else:  # pragma: no cover
            for i in self.base.validators + self.validators:
                if not i(res):
                    return ValidateResult(value=input_, flag=ResultFlag.VALID)
            if default is Empty:
                return ValidateResult(
                    error=MatchFailed(
                        lang.require("nepattern", "content_error").format(target=input_, expected=self._repr)
                    ),
                    flag=ResultFlag.ERROR,
                )
            if TYPE_CHECKING:
                default = cast(TDefault, default)
            return ValidateResult(default, flag=ResultFlag.DEFAULT)

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, AntiPattern) and self.base == other.base


TInput = TypeVar("TInput")


class CustomMatchPattern(BasePattern[TOrigin, TInput, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(
        self,
        origin: type[TOrigin],
        func: Callable[[BasePattern, TInput], TOrigin | None],
        alias: str | None = None,
    ):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=origin, alias=alias or func.__name__)
        self.__func__ = func
        self.match = func.__get__(self)  # type: ignore

    def __calc_eq__(self, other):  # pragma: no cover
        return isinstance(other, CustomMatchPattern) and self.__func__ == other.__func__


NONE = CustomMatchPattern(type(None), lambda _, __: None, alias="none")  # pragma: no cover


@final
class AnyPattern(BasePattern[Any, Any, Literal[MatchMode.KEEP]]):
    def __init__(self):
        super().__init__(mode=MatchMode.KEEP, origin=Any, alias="any")

    def match(self, input_: Any) -> Any:  # pragma: no cover
        return input_

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is AnyPattern


ANY = AnyPattern()
"""匹配任意内容的表达式"""


@final
class AnyStrPattern(BasePattern[str, Any, Literal[MatchMode.KEEP]]):
    def __init__(self):
        super().__init__(mode=MatchMode.KEEP, origin=str, alias="any_str")

    def match(self, input_: Any) -> str:
        return str(input_)

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is AnyStrPattern


AnyString = AnyStrPattern()
"""匹配任意内容并转为字符串的表达式"""


@final
class StrPattern(BasePattern[str, Union[str, bytes, bytearray], Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(
            mode=MatchMode.TYPE_CONVERT, origin=str, accepts=Union[str, bytes, bytearray], alias="str"
        )

    def match(self, input_: Any) -> str:
        if isinstance(input_, str):
            return input_.value if isinstance(input_, Enum) else input_
        elif isinstance(input_, (bytes, bytearray)):
            return input_.decode()
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected="str | bytes | bytearray"
            )
        )

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is StrPattern


STRING = StrPattern()


@final
class BytesPattern(BasePattern[bytes, Union[str, bytes, bytearray], Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(
            mode=MatchMode.TYPE_CONVERT, origin=bytes, accepts=Union[str, bytes, bytearray], alias="bytes"
        )

    def match(self, input_: Any) -> bytes:
        if isinstance(input_, bytes):
            return input_
        elif isinstance(input_, bytearray):
            return bytes(input_)
        elif isinstance(input_, str):
            return input_.encode()
        raise MatchFailed(
            lang.require("nepattern", "type_error").format(
                type=input_.__class__, target=input_, expected="bytes | str"
            )
        )

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is BytesPattern


BYTES = BytesPattern()


@final
class IntPattern(BasePattern[int, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=int, alias="int")

    def match(self, input_: Any) -> int:
        if isinstance(input_, int) and input_ is not True and input_ is not False:
            return input_
        if isinstance(input_, (str, bytes, bytearray)) and len(input_) > 4300:  # pragma: no cover
            raise ValueError("int too large to convert")
        try:
            return int(input_)
        except (ValueError, TypeError, OverflowError) as e:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="int")
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is IntPattern


INTEGER = IntPattern()
"""整形数表达式，只能接受整数样式的量"""


@final
class FloatPattern(BasePattern[float, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=float, alias="float")

    def match(self, input_: Any) -> float:
        if isinstance(input_, float):
            return input_

        try:
            return float(input_)
        except (TypeError, ValueError) as e:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="float")
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is FloatPattern


FLOAT = FloatPattern()
"""浮点数表达式"""


@final
class NumberPattern(BasePattern[Union[int, float], Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=Union[int, float], alias="number")  # type: ignore

    def match(self, input_: Any) -> int | float:
        if isinstance(input_, (float, int)):
            return input_
        try:
            res = float(input_)
            return int(res) if res.is_integer() else res
        except (ValueError, TypeError) as e:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="int | float")
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is NumberPattern


NUMBER = NumberPattern()
"""一般数表达式，既可以浮点数也可以整数 """


@final
class BoolPattern(BasePattern[bool, Union[str, bytes, bool], Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=bool, alias="bool")

    def match(self, input_: Any) -> bool:
        if input_ is True or input_ is False:
            return input_
        if isinstance(input_, bytes):  # pragma: no cover
            input_ = input_.decode()
        if isinstance(input_, str):
            input_ = input_.lower()
        if input_ == "true":
            return True
        if input_ == "false":
            return False
        raise MatchFailed(lang.require("nepattern", "content_error").format(target=input_, expected="bool"))

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is BoolPattern


BOOLEAN = BoolPattern()
"""布尔表达式，只能接受true或false样式的量"""


@final
class WideBoolPattern(BasePattern[bool, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=bool, alias="bool")

    BOOL_FALSE = {0, "0", "off", "f", "false", "n", "no"}
    BOOL_TRUE = {1, "1", "on", "t", "true", "y", "yes"}

    def match(self, input_: Any) -> bool:
        if input_ is True or input_ is False:
            return input_
        if isinstance(input_, bytes):  # pragma: no cover
            input_ = input_.decode()
        if isinstance(input_, str):
            input_ = input_.lower()
        try:
            if input_ in self.BOOL_TRUE:
                return True
            if input_ in self.BOOL_FALSE:
                return False
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="bool")
            )
        except (ValueError, TypeError) as e:
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected="bool"
                )
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is BoolPattern


WIDE_BOOLEAN = WideBoolPattern()
"""宽松布尔表达式，可以接受更多的布尔样式的量"""

LIST = BasePattern(r"(\[.+?\])", MatchMode.REGEX_CONVERT, list, alias="list")
TUPLE = BasePattern(r"(\(.+?\))", MatchMode.REGEX_CONVERT, tuple, alias="tuple")
SET = BasePattern(r"(\{.+?\})", MatchMode.REGEX_CONVERT, set, alias="set")
DICT = BasePattern(r"(\{.+?\})", MatchMode.REGEX_CONVERT, dict, alias="dict")

EMAIL = BasePattern(r"(?:[\w\.+-]+)@(?:[\w\.-]+)\.(?:[\w\.-]+)", MatchMode.REGEX_MATCH, alias="email")
"""匹配邮箱地址的表达式"""

IP = BasePattern(
    r"(?:(?:[01]{0,1}\d{0,1}\d|2[0-4]\d|25[0-5])\.){3}(?:[01]{0,1}\d{0,1}\d|2[0-4]\d|25[0-5]):?(?:\d+)?",
    MatchMode.REGEX_MATCH,
    alias="ip",
)
"""匹配Ip地址的表达式"""

URL = BasePattern(
    r"(?:\w+://)?[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+(?::[0-9]{1,5})?[-a-zA-Z0-9()@:%_\\\+\.~#?&//=]*",
    MatchMode.REGEX_MATCH,
    alias="url",
)
"""匹配网页链接的表达式"""


@final
class HexPattern(BasePattern[int, str, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=int, alias="hex", accepts=str)

    def match(self, input_: str) -> int:
        if not isinstance(input_, str):
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected="str"
                )
            )
        try:
            return int(input_, 16)
        except ValueError as e:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="hex")
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is HexPattern


HEX = HexPattern()
"""匹配16进制数的表达式"""

HEX_COLOR = BasePattern(r"(#[0-9a-fA-F]{6})", MatchMode.REGEX_CONVERT, str, lambda _, x: x[1][1:], "color")
"""匹配16进制颜色代码的表达式"""


@final
class DateTimePattern(BasePattern[datetime, Union[str, int, float], Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(
            mode=MatchMode.TYPE_CONVERT, origin=datetime, alias="datetime", accepts=Union[str, int, float]
        )

    def match(self, input_: Union[str, int, float]) -> datetime:
        if isinstance(input_, (int, float)):
            return datetime.fromtimestamp(input_)
        if not isinstance(input_, str):
            raise MatchFailed(
                lang.require("nepattern", "type_error").format(
                    type=input_.__class__, target=input_, expected="str | int | float"
                )
            )
        return DateParser.parse(input_)

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is DateTimePattern


DATETIME = DateTimePattern()
"""匹配时间的表达式"""


@final
class PathPattern(BasePattern[Path, Any, Literal[MatchMode.TYPE_CONVERT]]):
    def __init__(self):
        super().__init__(mode=MatchMode.TYPE_CONVERT, origin=Path, alias="path")

    def match(self, input_: Any) -> Path:
        if isinstance(input_, Path):
            return input_

        try:
            return Path(input_)
        except (ValueError, TypeError) as e:
            raise MatchFailed(
                lang.require("nepattern", "content_error").format(target=input_, expected="PathLike")
            ) from e

    def __calc_eq__(self, other):  # pragma: no cover
        return other.__class__ is PathPattern


PATH = PathPattern()

PathFile = BasePattern(
    mode=MatchMode.TYPE_CONVERT,
    origin=bytes,
    accepts=Path,
    previous=PATH,
    alias="filedata",
    converter=lambda _, x: x.read_bytes() if x.exists() and x.is_file() else None,
)


def combine(
    current: BasePattern[TOrigin, TInput, TMM],
    previous: BasePattern[TInput, Any, Any] | None = None,
    alias: str | None = None,
    validators: list[Callable[[TOrigin], bool]] | None = None,
) -> BasePattern[TOrigin, TInput, TMM]:
    _new = current.copy()
    if previous:
        _match = _new.match

        def match(self, input_):
            return _match(previous.match(input_))

        _new.match = match.__get__(_new)
    if alias:
        _new.alias = alias
        _new.refresh()
    if validators:
        _new.validators = validators
    return _new


DelimiterInt = combine(
    INTEGER,
    BasePattern(mode=MatchMode.VALUE_OPERATE, origin=str, converter=lambda _, x: x.replace(",", "_")),
    "DelimInt",
)
