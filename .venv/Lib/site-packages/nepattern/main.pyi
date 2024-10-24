from collections.abc import Mapping as ABCMap
from collections.abc import MutableSequence as ABCMuSeq
from collections.abc import Set as ABCSet
from types import UnionType
from typing import Any, Callable, ForwardRef, Iterable, Literal, TypeVar, overload

from .base import (
    DirectPattern,
    DirectTypePattern,
    ForwardRefPattern,
    IterMode,
    MappingPattern,
    RegexPattern,
    SequencePattern,
    SwitchPattern,
    UnionPattern,
)
from .core import BasePattern, MatchMode
from .util import RawStr, TPattern

T1 = TypeVar("T1")
T2 = TypeVar("T2")

@overload
def parser(
    item: str, extra: str = "allow"
) -> (
    BasePattern[str, str, Literal[MatchMode.REGEX_MATCH]] | DirectPattern[str] | RegexPattern | UnionPattern
): ...
@overload
def parser(item: RawStr, extra: str = "allow") -> DirectPattern[str]: ...
@overload
def parser(item: TPattern, extra: str = "allow") -> RegexPattern: ...
@overload
def parser(
    item: type[ABCMap[T1, T2]], extra: str = "allow"
) -> MappingPattern[T1, T2, Literal[IterMode.ALL]]: ...
@overload
def parser(
    item: type[ABCMuSeq[T1]], extra: str = "allow"
) -> SequencePattern[list[T1], Literal[IterMode.ALL]]: ...
@overload
def parser(
    item: type[tuple[T1, ...]], extra: str = "allow"
) -> SequencePattern[tuple[T1, ...], Literal[IterMode.ALL]]: ...
@overload
def parser(
    item: type[ABCSet[T1]], extra: str = "allow"
) -> SequencePattern[set[T1], Literal[IterMode.ALL]]: ...
@overload
def parser(item: type[T1], extra: str = "allow") -> BasePattern[T1, Any, Any] | DirectTypePattern[T1]: ...
@overload
def parser(item: ABCMap[T1, T2], extra: str = "allow") -> SwitchPattern[T2, T1]: ...
@overload
def parser(item: UnionType, extra: str = "allow") -> UnionPattern[Any]: ...
@overload
def parser(item: Iterable[T1 | type[T1]], extra: str = "allow") -> UnionPattern[T1]: ...
@overload
def parser(item: ForwardRef, extra: str = "allow") -> ForwardRefPattern: ...
@overload
def parser(
    item: Callable[[T1], T2], extra: str = "allow"
) -> BasePattern[T2, T1, Literal[MatchMode.TYPE_CONVERT]]: ...
@overload
def parser(item: T1, extra: str = "allow") -> BasePattern[T1, T1, Literal[MatchMode.KEEP]]: ...
